"""Selling in chat: products, customers (one person across channels), orders, payment links and delivery."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from core.crypto import EncryptedJSONField

ZERO = Decimal("0")


class ShopSettings(models.Model):
    workspace = models.OneToOneField("core.Workspace", on_delete=models.CASCADE, related_name="shop")
    currency = models.CharField(max_length=3, default="NPR")
    order_prefix = models.CharField(max_length=10, default="#")
    next_order_number = models.PositiveIntegerField(default=1001)
    delivery_inside_valley = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("100"))
    delivery_outside_valley = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("150"))
    bank_details = models.TextField(blank=True, help_text="Shown to customers who choose bank transfer / QR")
    # Payment gateways (the shop's own merchant accounts)
    khalti_live = models.BooleanField(default=False)
    esewa_live = models.BooleanField(default=False)
    esewa_merchant_code = models.CharField(max_length=60, blank=True)
    # Courier accounts
    ncm_live = models.BooleanField(default=False)
    ncm_from_branch = models.CharField(max_length=60, blank=True, default="TINKUNE")
    pathao_base_url = models.URLField(blank=True, default="https://api-hermes.pathao.com")
    pathao_store_id = models.CharField(max_length=30, blank=True)
    # Secrets: {"khalti_secret_key", "esewa_secret_key", "ncm_token", "pathao": {client_id, client_secret, username, password, access_token, expires_at}}
    secrets = EncryptedJSONField(blank=True, default=dict)
    # Messages sent to customers ({name}, {order}, {total}, {link}, {tracking}, {items})
    msg_order_summary = models.TextField(blank=True, default=(
        "Thank you {name}! 🙏 Your order {order}:\n{items}\nDelivery: {delivery}\nTotal: {total}\n\n{payment}"))
    msg_paid = models.TextField(blank=True, default="Payment received for order {order} ({total}). Thank you! We'll pack it right away. 📦")
    msg_shipped = models.TextField(blank=True, default="Your order {order} is on the way with {courier}! 🚚 Tracking: {tracking}")
    msg_delivered = models.TextField(blank=True, default="Your order {order} has been delivered. We hope you love it! ❤️")
    auto_message_paid = models.BooleanField(default=True)
    auto_message_shipped = models.BooleanField(default=True)
    auto_message_delivered = models.BooleanField(default=False)
    msg_out_for_delivery = models.TextField(blank=True, default="Good news {name}! Your order {order} is out for delivery today 🛵 Please keep your phone handy.")
    auto_message_out_for_delivery = models.BooleanField(default=True)
    # Book the courier by itself: "off", when the order is "paid", or when it's "confirmed" (paid or cash on delivery)
    AUTO_SHIP = [("off", "Off: staff presses Ship"), ("paid", "When paid online"), ("confirmed", "When confirmed (paid or COD)")]
    auto_ship = models.CharField(max_length=10, choices=AUTO_SHIP, default="off")
    default_courier = models.CharField(max_length=10, blank=True, default="", help_text="ncm / pathao")
    # How the shop's own eSewa / Khalti / bank account appears on payment screenshots (one per line)
    payment_receivers = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def for_workspace(cls, ws):
        obj, _ = cls.objects.get_or_create(workspace=ws)
        return obj

    def secret(self, key, default=""):
        return (self.secrets or {}).get(key, default)

    def __str__(self):
        return f"Shop settings for {self.workspace}"


class Product(models.Model):
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=60, blank=True)
    description = models.TextField(max_length=3000, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.IntegerField(null=True, blank=True, help_text="Empty = not tracked")
    variants = models.JSONField(default=list, blank=True, help_text='e.g. ["S", "M", "L"] or ["Red", "Blue"]')
    image = models.ForeignKey("publishing.MediaAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.5"))
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Customer(models.Model):
    """One real person, linked to their contacts on every channel (WhatsApp, Instagram, Messenger...)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or self.phone or str(self.id)[:8]


class Order(models.Model):
    STATUSES = [("new", "New"), ("confirmed", "Confirmed"), ("packed", "Packed"), ("shipped", "Shipped"),
                ("delivered", "Delivered"), ("cancelled", "Cancelled"), ("returned", "Returned")]
    PAYMENT_METHODS = [("cod", "Cash on delivery"), ("khalti", "Khalti"), ("esewa", "eSewa"),
                       ("bank", "Bank transfer / QR"), ("cash", "Cash (in store)")]
    PAYMENT_STATUSES = [("unpaid", "Unpaid"), ("pending", "Payment link sent"), ("paid", "Paid"), ("refunded", "Refunded")]
    COURIERS = [("", "Not shipped"), ("ncm", "Nepal Can Move"), ("pathao", "Pathao"), ("manual", "Other courier"),
                ("self", "Own delivery")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="orders")
    number = models.CharField(max_length=20)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    conversation = models.ForeignKey("inbox.Conversation", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="orders")
    status = models.CharField(max_length=12, choices=STATUSES, default="new", db_index=True)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default="cod")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUSES, default="unpaid", db_index=True)
    currency = models.CharField(max_length=3, default="NPR")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    # Delivery address (snapshot at order time)
    recipient_name = models.CharField(max_length=200, blank=True)
    recipient_phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    # Shipping
    courier = models.CharField(max_length=10, choices=COURIERS, blank=True, default="")
    courier_name = models.CharField(max_length=60, blank=True)
    courier_ref = models.CharField(max_length=60, blank=True, help_text="Courier's order id")
    tracking_id = models.CharField(max_length=80, blank=True)
    tracking_url = models.URLField(max_length=500, blank=True)
    delivery_status = models.CharField(max_length=120, blank=True)
    delivery_checked_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    history = models.JSONField(default=list, blank=True)  # [{at, text, by}]
    SOURCES = [("manual", "Team"), ("ai", "AI sales agent"), ("api", "API")]
    source = models.CharField(max_length=10, choices=SOURCES, default="manual")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("workspace", "number")
        indexes = [models.Index(fields=["workspace", "status", "-created_at"], name="order_ws_status_recent")]

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=200)
    variant = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class PaymentLink(models.Model):
    STATUSES = [("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed"), ("cancelled", "Cancelled")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payment_links")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")
    gateway = models.CharField(max_length=10, blank=True)  # chosen by the customer: khalti / esewa
    reference = models.CharField(max_length=100, blank=True)  # Khalti pidx / eSewa transaction_uuid
    txn_id = models.CharField(max_length=100, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    @property
    def url(self):
        return f"{settings.FRONTEND_URL}/pay/{self.id}"


class PaymentCheck(models.Model):
    """A payment screenshot a customer sent (eSewa / Khalti / bank / Fonepay), read by the AI and matched to an order.
    The AI never marks an order paid by itself: staff confirm with one tap (fake screenshots are common)."""

    VALID, CHECK, SUSPICIOUS, NOT_PAYMENT = "valid", "check", "suspicious", "not_payment"
    VERDICTS = [(VALID, "Looks valid"), (CHECK, "Needs a look"), (SUSPICIOUS, "Suspicious"), (NOT_PAYMENT, "Not a payment")]
    PENDING, CONFIRMED, REJECTED = "pending", "confirmed", "rejected"
    STATUSES = [(PENDING, "Waiting for staff"), (CONFIRMED, "Confirmed"), (REJECTED, "Rejected")]

    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="payment_checks")
    conversation = models.ForeignKey("inbox.Conversation", null=True, blank=True, on_delete=models.CASCADE, related_name="payment_checks")
    attachment = models.ForeignKey("inbox.Attachment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment_checks")
    app = models.CharField(max_length=20, blank=True)  # esewa / khalti / bank / fonepay / other
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    txn_id = models.CharField(max_length=100, blank=True, db_index=True)
    paid_on = models.CharField(max_length=60, blank=True, help_text="Date/time as shown on the screenshot")
    receiver = models.CharField(max_length=200, blank=True)
    sender = models.CharField(max_length=200, blank=True)
    verdict = models.CharField(max_length=12, choices=VERDICTS, default=CHECK)
    reasons = models.JSONField(default=list, blank=True)  # ["Amount matches order #1003", "⚠ Transaction ID used before"]
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Booking(models.Model):
    """A visit / appointment (counselling session, campus visit, clinic appointment, trial class...)."""

    BOOKED, CONFIRMED, DONE, NO_SHOW, CANCELLED = "booked", "confirmed", "done", "no_show", "cancelled"
    STATUSES = [(BOOKED, "Booked"), (CONFIRMED, "Confirmed"), (DONE, "Visited"), (NO_SHOW, "Didn't come"),
                (CANCELLED, "Cancelled")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="bookings")
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    conversation = models.ForeignKey("inbox.Conversation", null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    purpose = models.CharField(max_length=300, blank=True, help_text="e.g. IELTS + Australia, Feb intake")
    starts_at = models.DateTimeField(db_index=True)
    minutes = models.PositiveSmallIntegerField(default=30)
    status = models.CharField(max_length=10, choices=STATUSES, default=BOOKED, db_index=True)
    note = models.TextField(blank=True)
    source = models.CharField(max_length=10, default="manual")  # manual / ai
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.name or self.phone} @ {self.starts_at:%Y-%m-%d %H:%M}"
