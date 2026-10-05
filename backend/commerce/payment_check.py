"""Payment screenshots: match what the AI read to an order and decide how much to trust it.

The AI never marks an order paid. It sorts screenshots into "looks valid" / "needs a look" / "suspicious" and staff
confirm with one tap. Checks: amount = order total, success status, the shop's own account as receiver, a recent date,
a transaction id never used before, and no visible signs of editing.
"""
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import Order, PaymentCheck, ShopSettings
from .services import mark_paid, money

SUCCESS_WORDS = ("success", "successful", "complete", "completed", "paid", "sent", "transferred", "done", "सफल")
FAIL_WORDS = ("fail", "failed", "pending", "processing", "cancel", "declined", "reversed")
APP_LABELS = {"esewa": "eSewa", "khalti": "Khalti", "imepay": "IME Pay", "fonepay": "Fonepay", "bank": "Bank transfer"}


def _norm(text):
    return re.sub(r"[^a-z0-9ऀ-ॿ]", "", (text or "").lower())


def _parse_date(text):
    """Best effort: the date forms Nepali wallets and banks print (2026-10-04 11:34, 04/10/2026, Oct 04 2026...)."""
    t = " ".join(re.sub(r"[,T|]", " ", text or "").split())
    if not t:
        return None
    toks = t.split(" ")
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%b %d %Y", "%d %B %Y", "%B %d %Y",
               "%d-%b-%Y", "%d %b %y"]
    for n in (3, 2, 1):
        chunk = " ".join(toks[:n])
        for f in formats:
            try:
                return datetime.strptime(chunk, f).date()
            except ValueError:
                continue
    return None


def candidate_orders(conversation):
    """Unpaid orders this customer might be paying for (newest first)."""
    qs = Order.objects.filter(workspace=conversation.workspace, payment_status__in=["unpaid", "pending"]).exclude(
        status__in=["cancelled", "returned"])
    customer_id = conversation.contact.customer_id
    by_conv = list(qs.filter(conversation=conversation).order_by("-created_at")[:10])
    by_customer = list(qs.filter(customer_id=customer_id).order_by("-created_at")[:10]) if customer_id else []
    seen, out = set(), []
    for o in by_conv + by_customer:
        if o.pk not in seen:
            seen.add(o.pk)
            out.append(o)
    return out


def evaluate(workspace, conversation, note, exclude_id=None):
    """(verdict, reasons, order) for what the AI read off a screenshot."""
    if not note.get("is_payment"):
        return PaymentCheck.NOT_PAYMENT, [], None
    shop = ShopSettings.for_workspace(workspace)
    good, warn, bad = [], [], []
    try:
        amount = Decimal(str(note["amount"])) if note.get("amount") is not None else None
    except (InvalidOperation, ValueError):
        amount = None

    order = None
    orders = candidate_orders(conversation) if conversation else []
    if amount is None:
        bad.append("Couldn't read the amount")
    else:
        order = next((o for o in orders if abs(o.total - amount) <= Decimal("1")), None)
        if order:
            good.append(f"Amount {money(amount)} matches order {order.number}")
        elif orders:
            totals = ", ".join(f"{o.number} = {money(o.total, o.currency)}" for o in orders[:3])
            bad.append(f"Amount {money(amount)} doesn't match any unpaid order ({totals})")
            order = orders[0]
        else:
            warn.append(f"Amount {money(amount)}, but this customer has no unpaid order")

    status = (note.get("status") or "").lower()
    if any(w in status for w in FAIL_WORDS):
        bad.append(f"Status on the screenshot is \"{note.get('status')}\"")
    elif any(w in status for w in SUCCESS_WORDS):
        good.append(f"Status: {note.get('status')}")
    else:
        warn.append("No success status visible")

    receivers = [_norm(r) for r in (shop.payment_receivers or "").splitlines() if len(_norm(r)) >= 3]
    got = _norm(note.get("receiver"))
    if receivers:
        if got and any(r in got or got in r for r in receivers):
            good.append(f"Paid to your account ({note.get('receiver')})")
        elif got:
            bad.append(f"Receiver \"{note.get('receiver')}\" isn't one of your accounts")
        else:
            warn.append("Receiver not visible")
    else:
        warn.append("Add your eSewa / Khalti / bank account names in Settings → Shop so receivers can be checked")

    txn = (note.get("txn_id") or "").strip()
    if not txn:
        warn.append("No transaction ID visible")
    else:
        dup = PaymentCheck.objects.filter(workspace=workspace, txn_id__iexact=txn).exclude(pk=exclude_id).exclude(
            status=PaymentCheck.REJECTED).first()
        if dup:
            bad.append(f"Transaction ID {txn} was already sent before ({dup.created_at:%d %b})")
        else:
            good.append(f"Transaction ID {txn} is new")

    day = _parse_date(note.get("date_time"))
    today = timezone.localdate()
    if day is None:
        warn.append("Couldn't read the payment date")
    elif day > today + timedelta(days=1):
        bad.append(f"Date {note.get('date_time')} is in the future")
    elif order and day < timezone.localtime(order.created_at).date() - timedelta(days=1):
        bad.append(f"Paid on {note.get('date_time')}, before the order was placed")
    elif day < today - timedelta(days=3):
        bad.append(f"Payment date {note.get('date_time')} is more than 3 days old")
    else:
        good.append(f"Date: {note.get('date_time')}")

    for sign in note.get("edit_signs") or []:
        bad.append(f"Possible editing: {sign}")

    verdict = PaymentCheck.SUSPICIOUS if bad else (PaymentCheck.CHECK if warn else PaymentCheck.VALID)
    reasons = [f"✓ {g}" for g in good] + [f"? {w}" for w in warn] + [f"⚠ {b}" for b in bad]
    return verdict, reasons, order


def record(attachment, conversation, note):
    """Store a PaymentCheck for a screenshot and leave a note for the team in the conversation."""
    from inbox.models import Message
    ws = conversation.workspace
    verdict, reasons, order = evaluate(ws, conversation, note)
    if verdict == PaymentCheck.NOT_PAYMENT:
        return None
    try:
        amount = Decimal(str(note["amount"])) if note.get("amount") is not None else None
    except (InvalidOperation, ValueError):
        amount = None
    check = PaymentCheck.objects.create(
        workspace=ws, conversation=conversation, attachment=attachment, order=order, app=note.get("app", ""),
        amount=amount, txn_id=note.get("txn_id", ""), paid_on=note.get("date_time", ""),
        receiver=note.get("receiver", ""), sender=note.get("sender", ""), verdict=verdict, reasons=reasons)
    head = {PaymentCheck.VALID: "✅ Payment screenshot looks valid", PaymentCheck.CHECK: "🧾 Payment screenshot: please check",
            PaymentCheck.SUSPICIOUS: "⚠️ Suspicious payment screenshot"}[verdict]
    app = APP_LABELS.get(check.app, check.app or "payment")
    amt = money(amount) if amount is not None else "amount unreadable"
    target = f" for order {order.number}" if order else ""
    Message.objects.create(
        conversation=conversation, direction="out", is_note=True, bot="ai", sender_name="Payment check",
        status="sent", sent_at=timezone.now(),
        text=f"{head}: {amt} via {app}{target}.\n" + "\n".join(reasons) +
             "\nConfirm or reject it in the customer panel → Payments. The AI never marks orders paid by itself.")
    return check


@transaction.atomic
def confirm(check, user, order=None):
    check = PaymentCheck.objects.select_for_update().get(pk=check.pk)
    if check.status != PaymentCheck.PENDING:
        return check
    order = order or check.order
    if order is None:
        raise ValueError("Pick the order this payment is for.")
    check.order, check.status, check.reviewed_by, check.reviewed_at = order, PaymentCheck.CONFIRMED, user, timezone.now()
    check.save()
    via = f"{APP_LABELS.get(check.app, check.app or 'screenshot')} (screenshot checked)"
    mark_paid(order, via=via, txn=check.txn_id, user=user)
    return check


def reject(check, user, message=""):
    if check.status != PaymentCheck.PENDING:
        return check
    check.status, check.reviewed_by, check.reviewed_at = PaymentCheck.REJECTED, user, timezone.now()
    check.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    if message and check.conversation_id:
        from inbox.services import send_reply
        send_reply(check.conversation, message[:1000], user=user)
    return check


def check_json(c):
    from inbox import media
    return {
        "id": c.id, "app": c.app, "app_label": APP_LABELS.get(c.app, c.app or "Payment"),
        "amount": str(c.amount) if c.amount is not None else None, "txn_id": c.txn_id, "paid_on": c.paid_on,
        "receiver": c.receiver, "sender": c.sender, "verdict": c.verdict, "verdict_label": c.get_verdict_display(),
        "reasons": c.reasons, "status": c.status, "created_at": c.created_at,
        "order": {"id": str(c.order_id), "number": c.order.number, "total": str(c.order.total),
                  "payment_status": c.order.payment_status} if c.order_id else None,
        "image": media.as_json(c.attachment) if c.attachment_id and c.attachment else None,
        "conversation_id": str(c.conversation_id) if c.conversation_id else None,
        "reviewed_by": (c.reviewed_by.get_full_name() or c.reviewed_by.email) if c.reviewed_by_id else "",
    }
