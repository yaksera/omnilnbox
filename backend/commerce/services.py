"""Order logic shared by the API, payment callbacks and the worker."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from . import delivery
from .models import Customer, Order, OrderItem, PaymentLink, Product, ShopSettings

logger = logging.getLogger(__name__)
MONEY = Decimal("0.01")


def money(amount, currency="NPR"):
    amount = Decimal(amount)
    if currency == "NPR":
        return f"Rs {amount.quantize(Decimal('1')):,}"
    return f"${amount.quantize(MONEY):,}"


def _emit(event, order):
    from developers.events import emit, order_data
    emit(event, order.workspace_id, order_data(order))


def log(order, text, user=None):
    order.history = [*(order.history or []), {"at": timezone.now().isoformat(), "text": text[:300],
                                               "by": (user.get_full_name() or user.email) if user else "OmniInbox"}]


# ------------------------------------------------------------------ customers
def normalize_phone(phone):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("977") and len(digits) > 10:
        digits = digits[3:]
    return digits[-10:] if len(digits) >= 10 else digits


def customer_for_contact(contact, **fields):
    """The Customer behind a chat contact. Reuses a customer with the same phone (same person on another app)."""
    if contact.customer_id:
        cust = contact.customer
    else:
        phone = normalize_phone(fields.get("phone") or contact.handle)
        cust = Customer.objects.filter(workspace=contact.workspace, phone=phone).first() if len(phone) >= 10 else None
        if cust is None:
            cust = Customer.objects.create(workspace=contact.workspace, name=contact.name, phone=phone if len(phone) >= 10 else "")
        contact.customer = cust
        contact.save(update_fields=["customer"])
    changed = False
    for key in ("name", "phone", "address", "city", "district"):
        value = fields.get(key)
        if key == "phone":
            value = normalize_phone(value)
        if value and getattr(cust, key) != value:
            setattr(cust, key, value)
            changed = True
    if changed:
        cust.save()
    return cust


def merge_customers(keep, other):
    """Move everything from `other` into `keep` and delete `other`."""
    with transaction.atomic():
        other.contacts.update(customer=keep)
        other.orders.update(customer=keep)
        for field in ("name", "phone", "email", "address", "city", "district"):
            if not getattr(keep, field) and getattr(other, field):
                setattr(keep, field, getattr(other, field))
        if other.notes:
            keep.notes = f"{keep.notes}\n{other.notes}".strip()
        keep.save()
        other.delete()
    return keep


# ------------------------------------------------------------------ orders
def next_number(ws):
    with transaction.atomic():
        shop = ShopSettings.objects.select_for_update().get(pk=ShopSettings.for_workspace(ws).pk)
        number = f"{shop.order_prefix}{shop.next_order_number}"
        shop.next_order_number += 1
        shop.save(update_fields=["next_order_number"])
    return number


def recalc(order):
    subtotal = sum((i.unit_price * i.quantity for i in order.items.all()), Decimal("0"))
    order.subtotal = subtotal.quantize(MONEY)
    order.delivery_charge = Decimal(order.delivery_charge or 0).quantize(MONEY)
    order.discount = Decimal(order.discount or 0).quantize(MONEY)
    order.total = max(Decimal("0"), order.subtotal + order.delivery_charge - order.discount).quantize(MONEY)


@transaction.atomic
def save_order(ws, data, user=None, order=None):
    """Create or update an order from validated data (items: [{product_id|name, variant, quantity, unit_price}])."""
    creating = order is None
    if creating:
        order = Order(workspace=ws, number=next_number(ws), created_by=user,
                      currency=ShopSettings.for_workspace(ws).currency)
    for key in ("payment_method", "delivery_charge", "discount", "recipient_name", "recipient_phone", "address", "city",
                "district", "note", "conversation", "customer"):
        if key in data:
            setattr(order, key, data[key])
    order.save()
    if "items" in data:
        # give back stock of the old lines, take stock for the new ones
        for old in order.items.select_related("product"):
            if old.product and old.product.stock is not None:
                Product.objects.filter(pk=old.product_id).update(stock=F("stock") + old.quantity)
        order.items.all().delete()
        for it in data["items"]:
            product = Product.objects.filter(workspace=ws, id=it.get("product_id")).first() if it.get("product_id") else None
            OrderItem.objects.create(
                order=order, product=product, name=(it.get("name") or (product.name if product else "Item"))[:200],
                variant=str(it.get("variant") or "")[:100], quantity=max(1, int(it.get("quantity") or 1)),
                unit_price=Decimal(str(it.get("unit_price") if it.get("unit_price") not in (None, "") else (product.price if product else 0))),
            )
            if product and product.stock is not None:
                Product.objects.filter(pk=product.pk).update(stock=F("stock") - max(1, int(it.get("quantity") or 1)))
    recalc(order)
    if creating:
        log(order, f"Order created ({order.get_payment_method_display()})", user)
    order.save()
    if creating:
        _emit("order.created", order)
    if order.customer is None and order.conversation_id:
        order.customer = customer_for_contact(order.conversation.contact, name=order.recipient_name,
                                              phone=order.recipient_phone, address=order.address,
                                              city=order.city, district=order.district)
        order.save(update_fields=["customer"])
    return order


def items_text(order):
    lines = []
    for i in order.items.all():
        variant = f" ({i.variant})" if i.variant else ""
        lines.append(f"• {i.quantity} × {i.name}{variant} = {money(i.unit_price * i.quantity, order.currency)}")
    return "\n".join(lines)


def render(template, order, **extra):
    shop = ShopSettings.for_workspace(order.workspace)
    first = (order.recipient_name or (order.customer.name if order.customer else "") or "").split(" ")[0] or "there"
    values = {
        "name": first, "order": order.number, "total": money(order.total, order.currency), "items": items_text(order),
        "delivery": money(order.delivery_charge, order.currency) if order.delivery_charge else "Free",
        "tracking": order.tracking_url or order.tracking_id or "", "courier": order.courier_name or order.get_courier_display(),
        "shop": order.workspace.name, "bank": shop.bank_details, "link": "", "payment": "", **extra,
    }
    text = template or ""
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text.strip()


def payment_line(order, link=None):
    shop = ShopSettings.for_workspace(order.workspace)
    if order.payment_status == "paid":
        return "Payment: received ✅"
    if link is not None:
        return f"Pay online (Khalti / eSewa): {link.url}"
    if order.payment_method == "bank" and shop.bank_details:
        return f"Please pay by bank transfer / QR:\n{shop.bank_details}"
    if order.payment_method == "cod":
        return f"Payment: cash on delivery ({money(order.total, order.currency)})"
    return ""


def message_customer(order, text, user=None):
    """Send a message in the order's conversation (if it came from a chat)."""
    if not order.conversation_id or not text:
        return None
    from inbox.services import send_reply
    return send_reply(order.conversation, text, user=user, bot="" if user else "rule")


def create_payment_link(order):
    link = order.payment_links.filter(status="pending", amount=order.total).first()
    if link is None:
        link = PaymentLink.objects.create(order=order, amount=order.total)
    if order.payment_status == "unpaid":
        order.payment_status = "pending"
        log(order, f"Payment link created ({money(order.total, order.currency)})")
        order.save(update_fields=["payment_status", "history", "updated_at"])
    return link


def mark_paid(order, via="", txn="", user=None):
    if order.payment_status == "paid":
        return order
    order.payment_status, order.paid_at = "paid", timezone.now()
    if order.status == "new":
        order.status = "confirmed"
    log(order, f"Payment received{f' via {via}' if via else ''}{f' ({txn})' if txn else ''}", user)
    order.save()
    _emit("order.paid", order)
    shop = ShopSettings.for_workspace(order.workspace)
    if shop.auto_message_paid and order.conversation_id:
        message_customer(order, render(shop.msg_paid, order))
    if order.conversation_id:
        _team_note(order, f"💰 Order {order.number} paid: {money(order.total, order.currency)}{f' via {via}' if via else ''}.")
    schedule_auto_ship(order)
    return order


def _team_note(order, text):
    if not order.conversation_id:
        return
    from inbox.models import Message
    Message.objects.create(conversation=order.conversation, direction="out", is_note=True, bot="rule",
                           sender_name="Orders", status="sent", sent_at=timezone.now(), text=text)


# ------------------------------------------------------------------ automatic courier booking
def should_auto_ship(order, shop=None):
    shop = shop or ShopSettings.for_workspace(order.workspace)
    if shop.auto_ship == "off" or not shop.default_courier or order.courier or order.status not in ("confirmed", "packed"):
        return False
    from billing.plans import F_COURIERS
    if not order.workspace.has_feature(F_COURIERS):
        return False
    if shop.auto_ship == "paid":
        return order.payment_status == "paid"
    return order.payment_status == "paid" or order.payment_method == "cod"


def schedule_auto_ship(order):
    """Book the shop's default courier once the order is paid / confirmed (Settings → Shop → Delivery)."""
    if not should_auto_ship(order):
        return
    from django.conf import settings as dj
    if getattr(dj, "BACKGROUND_SYNC", False):
        auto_ship(order.pk)
        return
    import threading

    def job():
        from django.db import close_old_connections
        close_old_connections()
        try:
            auto_ship(order.pk)
        finally:
            close_old_connections()
    transaction.on_commit(lambda: threading.Thread(target=job, daemon=True).start())


def auto_ship(order_id):
    order = Order.objects.select_related("workspace", "conversation").filter(pk=order_id).first()
    if order is None:
        return None
    shop = ShopSettings.for_workspace(order.workspace)
    if not should_auto_ship(order, shop):
        return order
    courier = delivery.couriers(shop).get(shop.default_courier)
    try:
        if courier is None:
            raise delivery.DeliveryError("The default courier isn't connected any more.")
        opts = courier.guess_location(order) if shop.default_courier == "pathao" else {}
        ship(order, shop.default_courier, opts)
        _team_note(order, f"🚚 {order.courier_name} booked automatically for order {order.number}"
                          f"{f' (tracking {order.tracking_id})' if order.tracking_id else ''}.")
    except delivery.DeliveryError as exc:
        order.refresh_from_db()
        log(order, f"Automatic courier booking failed: {exc}")
        order.save(update_fields=["history", "updated_at"])
        _team_note(order, f"⚠️ Couldn't book the courier automatically for order {order.number}: {exc} "
                          "Press Ship on the order to book it.")
    return order


def set_status(order, status, user=None, notify=True):
    if status == order.status:
        return order
    old = order.get_status_display()
    order.status = status
    now = timezone.now()
    if status == "shipped" and not order.shipped_at:
        order.shipped_at = now
    if status == "delivered":
        order.delivered_at = order.delivered_at or now
        if order.payment_method == "cod" and order.payment_status != "paid":
            order.payment_status, order.paid_at = "paid", now  # courier collected the cash
    log(order, f"Status: {old} → {order.get_status_display()}", user)
    order.save()
    _emit("order.status_changed", order)
    if status == "confirmed":
        schedule_auto_ship(order)
    shop = ShopSettings.for_workspace(order.workspace)
    if notify and order.conversation_id:
        if status == "shipped" and shop.auto_message_shipped:
            message_customer(order, render(shop.msg_shipped, order))
        elif status == "delivered" and shop.auto_message_delivered:
            message_customer(order, render(shop.msg_delivered, order))
    return order


def ship(order, courier_key, opts, user=None):
    shop = ShopSettings.for_workspace(order.workspace)
    if courier_key in ("manual", "self"):
        order.courier = courier_key
        order.courier_name = (opts.get("courier_name") or ("Own delivery" if courier_key == "self" else "Courier"))[:60]
        order.tracking_id = str(opts.get("tracking_id") or "")[:80]
        url = str(opts.get("tracking_url") or "")
        order.tracking_url = url[:500] if url.startswith(("https://", "http://")) else ""
    else:
        courier = delivery.couriers(shop).get(courier_key)
        if courier is None:
            raise delivery.DeliveryError("Connect this courier first in Settings → Shop → Delivery.")
        if not (order.recipient_name and order.recipient_phone and order.address):
            raise delivery.DeliveryError("Add the customer's name, phone and address to the order first.")
        result = courier.create(order, opts)
        order.courier, order.courier_name = courier_key, courier.label
        order.courier_ref, order.tracking_id, order.tracking_url = result["courier_ref"], result["tracking_id"], result["tracking_url"]
        if result.get("charge"):
            log(order, f"{courier.label} delivery charge: {result['charge']}")
    order.delivery_status = "Booked"
    log(order, f"Shipped with {order.courier_name}{f' (tracking {order.tracking_id})' if order.tracking_id else ''}", user)
    order.save()
    return set_status(order, "shipped", user)


def sync_deliveries(limit=100):
    """Worker: refresh courier status for shipped orders (every ~30 min per order)."""
    now, updated = timezone.now(), 0
    qs = (Order.objects.filter(status="shipped", courier__in=["ncm", "pathao"])
          .exclude(courier_ref="").select_related("workspace")[:limit])
    for order in qs:
        if order.delivery_checked_at and now - order.delivery_checked_at < timedelta(minutes=30):
            continue
        courier = delivery.couriers(ShopSettings.for_workspace(order.workspace)).get(order.courier)
        order.delivery_checked_at = now
        if courier is None:
            order.save(update_fields=["delivery_checked_at"])
            continue
        try:
            text = courier.status(order)
        except delivery.DeliveryError as exc:
            logger.info("Delivery status for %s failed: %s", order.number, exc)
            order.save(update_fields=["delivery_checked_at"])
            continue
        changed = bool(text and text != order.delivery_status)
        if changed:
            order.delivery_status = text[:120]
            log(order, f"{order.courier_name}: {text}")
            updated += 1
        order.save()
        shop = ShopSettings.for_workspace(order.workspace)
        if changed and delivery.is_out_for_delivery(text) and shop.auto_message_out_for_delivery \
                and order.conversation_id and not any(h.get("text") == "Customer told the order is out for delivery" for h in order.history):
            message_customer(order, render(shop.msg_out_for_delivery, order))
            log(order, "Customer told the order is out for delivery")
            order.save(update_fields=["history"])
        if delivery.is_delivered(text):
            set_status(order, "delivered")
        elif delivery.is_returned(text):
            set_status(order, "returned", notify=False)
    return updated
