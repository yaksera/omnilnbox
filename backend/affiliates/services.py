"""Affiliate business rules: attribution, commissions, balances and payouts."""
import hashlib
import logging
import re
import secrets
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Affiliate, Click, Commission, Payout, Referral

logger = logging.getLogger(__name__)

CODE_RE = re.compile(r"^[A-Z0-9]{4,20}$")
RESERVED_CODES = {"ADMIN", "OMNI", "OMNIINBOX", "TEST", "FREE", "DISCOUNT", "PROMO", "SUPPORT", "BILLING"}
CURRENCIES = ("NPR", "USD")


class AffiliateError(Exception):
    """A rule was broken; the message is shown to the user as-is."""


# ------------------------------------------------------------------ settings
def default_rate():
    return Decimal(str(settings.AFFILIATE_COMMISSION_RATE))


def hold_days():
    return int(settings.AFFILIATE_HOLD_DAYS)


def min_payout(currency):
    return Decimal(str(settings.AFFILIATE_MIN_PAYOUT.get(currency, 0)))


def program_info():
    return {
        "rate": str(default_rate()), "hold_days": hold_days(),
        "min_payout": {c: str(min_payout(c)) for c in CURRENCIES},
        "link_base": f"{settings.FRONTEND_URL}/r/",
    }


# ------------------------------------------------------------------ codes
def normalize_code(code):
    return re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()[:20]


def validate_new_code(code, exclude_id=None):
    code = normalize_code(code)
    if not CODE_RE.match(code):
        raise AffiliateError("Use 4-20 letters or numbers for your code (e.g. RAM2026).")
    if code in RESERVED_CODES:
        raise AffiliateError("That code is reserved. Please pick another.")
    if Affiliate.objects.filter(code=code).exclude(id=exclude_id).exists():
        raise AffiliateError("That code is already taken. Please pick another.")
    return code


def suggest_code(user):
    base = normalize_code(user.first_name or user.email.split("@")[0])[:10] or "OMNI"
    if len(base) < 3:
        base = (base + "OMNI")[:4]
    for _ in range(20):
        code = f"{base}{secrets.randbelow(900) + 100}"
        if code not in RESERVED_CODES and not Affiliate.objects.filter(code=code).exists():
            return code
    return f"OMNI{secrets.token_hex(4).upper()}"


def find_active(code):
    code = normalize_code(code)
    if not code:
        return None
    return Affiliate.objects.select_related("user").filter(code=code, status=Affiliate.APPROVED).first()


# ------------------------------------------------------------------ attribution
def record_click(code, request, landing="", referrer=""):
    affiliate = find_active(code)
    if affiliate is None:
        return None
    from accounts.audit import client_ip
    raw = f"{client_ip(request)}|{request.META.get('HTTP_USER_AGENT', '')[:200]}|{timezone.localdate()}"
    Click.objects.create(affiliate=affiliate, visitor=hashlib.sha256(raw.encode()).hexdigest()[:32],
                         landing=str(landing)[:200], referrer=str(referrer)[:300])
    return affiliate


def is_own_workspace(affiliate, workspace):
    return workspace.memberships.filter(user_id=affiliate.user_id).exists()


def attach_referral(workspace, code, source="code"):
    """Link a workspace to the affiliate who referred it. Raises AffiliateError with a friendly reason."""
    from billing.models import Payment
    affiliate = find_active(code)
    if affiliate is None:
        raise AffiliateError("This promo code isn't valid.")
    if Referral.objects.filter(workspace=workspace).exists():
        raise AffiliateError("A promo code has already been applied to this workspace.")
    if is_own_workspace(affiliate, workspace):
        raise AffiliateError("You can't use your own promo code.")
    if Payment.objects.filter(workspace=workspace, status=Payment.STATUS_PAID).exists():
        raise AffiliateError("Promo codes can only be added before the first payment.")
    return Referral.objects.create(workspace=workspace, affiliate=affiliate, source=source if source in ("link", "code") else "code")


# ------------------------------------------------------------------ commissions
def _quantize(amount, currency):
    return amount.quantize(Decimal("1") if currency == "NPR" else Decimal("0.01"), rounding=ROUND_HALF_UP)


def record_commission(payment):
    """Called when a subscription payment is confirmed. Idempotent; never raises."""
    try:
        with transaction.atomic():
            referral = Referral.objects.select_related("affiliate").filter(workspace_id=payment.workspace_id).first()
            if referral is None or not referral.affiliate.is_active:
                return None
            affiliate = referral.affiliate
            if is_own_workspace(affiliate, payment.workspace):
                return None  # the affiliate joined the workspace later: no self-commission
            if Commission.objects.filter(payment=payment).exists():
                return None
            rate = affiliate.commission_rate
            amount = _quantize(Decimal(payment.amount) * rate, payment.currency)
            if amount <= 0:
                return None
            paid_at = payment.paid_at or timezone.now()
            commission = Commission.objects.create(
                affiliate=affiliate, referral=referral, payment=payment, base_amount=payment.amount, rate=rate,
                amount=amount, currency=payment.currency, available_at=paid_at + timedelta(days=hold_days()),
            )
            logger.info("Affiliate %s earned %s %s on payment %s", affiliate.code, amount, payment.currency, payment.id)
            return commission
    except Exception:  # noqa: BLE001 - a commission problem must never block a customer's payment
        logger.exception("Couldn't record affiliate commission for payment %s", payment.id)
        return None


def _money(qs):
    out = {c: Decimal("0") for c in CURRENCIES}
    for row in qs.values("currency").annotate(total=Sum("amount")):
        out[row["currency"]] = row["total"] or Decimal("0")
    return {c: str(_quantize(v, c)) for c, v in out.items()}


def balances(affiliate):
    """Per-currency totals: holding (refund window), available, requested (in a payout), paid, lifetime."""
    now = timezone.now()
    unpaid = affiliate.commissions.filter(status=Commission.PENDING)
    return {
        "holding": _money(unpaid.filter(payout__isnull=True, available_at__gt=now)),
        "available": _money(unpaid.filter(payout__isnull=True, available_at__lte=now)),
        "requested": _money(unpaid.filter(payout__isnull=False)),
        "paid": _money(affiliate.commissions.filter(status=Commission.PAID)),
        "lifetime": _money(affiliate.commissions.exclude(status=Commission.VOID)),
    }


def workspace_status(ws, now=None):
    now = now or timezone.now()
    if ws.plan == "free":
        return "free"
    if ws.plan_expires_at and now >= ws.plan_expires_at:
        return "cancelled"
    if ws.is_trialing:
        return "trial"
    return "subscribed"


def stats(affiliate):
    now = timezone.now()
    referrals = list(affiliate.referrals.select_related("workspace"))
    paying = sum(1 for r in referrals if workspace_status(r.workspace, now) == "subscribed")
    return {
        "clicks": affiliate.clicks.count(),
        "unique_visitors": affiliate.clicks.values("visitor").distinct().count(),
        "clicks_30d": affiliate.clicks.filter(created_at__gte=now - timedelta(days=30)).count(),
        "signups": len(referrals),
        "paying": paying,
    }


# ------------------------------------------------------------------ payouts
@transaction.atomic
def request_payout(affiliate, currency):
    affiliate = Affiliate.objects.select_for_update().get(pk=affiliate.pk)
    if not affiliate.is_active:
        raise AffiliateError("Your affiliate account isn't active.")
    if currency not in CURRENCIES:
        raise AffiliateError("Choose NPR or USD.")
    if not affiliate.payout_method or not (affiliate.payout_details or {}).get("account_number"):
        raise AffiliateError("Add your eSewa, Khalti or bank details first.")
    if affiliate.payouts.filter(status=Payout.REQUESTED, currency=currency).exists():
        raise AffiliateError("You already have a payout request being processed.")
    ready = list(affiliate.commissions.select_for_update().filter(
        status=Commission.PENDING, payout__isnull=True, currency=currency, available_at__lte=timezone.now()))
    total = sum((c.amount for c in ready), Decimal("0"))
    minimum = min_payout(currency)
    if total < minimum or total <= 0:
        label = f"Rs {minimum:,.0f}" if currency == "NPR" else f"${minimum:,.2f}"
        raise AffiliateError(f"You can request a payout once your available balance reaches {label}.")
    payout = Payout.objects.create(affiliate=affiliate, amount=total, currency=currency,
                                   method=affiliate.payout_method, details=affiliate.payout_details)
    Commission.objects.filter(id__in=[c.id for c in ready]).update(payout=payout)
    return payout


@transaction.atomic
def mark_payout_paid(payout, reference="", note=""):
    payout = Payout.objects.select_for_update().get(pk=payout.pk)
    if payout.status != Payout.REQUESTED:
        raise AffiliateError("This payout was already processed.")
    payout.status, payout.reference, payout.note, payout.processed_at = Payout.PAID, reference[:120], note[:300], timezone.now()
    payout.save()
    payout.commissions.update(status=Commission.PAID)
    return payout


@transaction.atomic
def reject_payout(payout, note=""):
    payout = Payout.objects.select_for_update().get(pk=payout.pk)
    if payout.status != Payout.REQUESTED:
        raise AffiliateError("This payout was already processed.")
    payout.status, payout.note, payout.processed_at = Payout.REJECTED, note[:300], timezone.now()
    payout.save()
    payout.commissions.update(payout=None)  # back to the affiliate's available balance
    return payout


def void_commission(commission, reason=""):
    """E.g. the customer was refunded. Not possible once paid out or while in a payout request."""
    if commission.status != Commission.PENDING or commission.payout_id:
        raise AffiliateError("Only unpaid commissions that aren't in a payout request can be voided.")
    commission.status, commission.void_reason = Commission.VOID, reason[:200]
    commission.save(update_fields=["status", "void_reason"])
    return commission
