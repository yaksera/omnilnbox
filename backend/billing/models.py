import uuid

from django.conf import settings
from django.db import models


class Payment(models.Model):
    """One checkout attempt for a plan period. Activated only after server-side verification."""

    GATEWAYS = [("khalti", "Khalti"), ("esewa", "eSewa"), ("stripe", "Card (Stripe)"), ("manual", "Manual")]
    STATUS_PENDING, STATUS_PAID, STATUS_FAILED = "pending", "paid", "failed"
    STATUSES = [(STATUS_PENDING, "Pending"), (STATUS_PAID, "Paid"), (STATUS_FAILED, "Failed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="payments")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    plan = models.CharField(max_length=20)
    cycle = models.CharField(max_length=10)
    extra_seats = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gateway = models.CharField(max_length=10, choices=GATEWAYS)
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_PENDING, db_index=True)
    reference = models.CharField(max_length=200, blank=True, db_index=True,
                                 help_text="Gateway reference: Khalti pidx / eSewa transaction_uuid / Stripe session id")
    gateway_txn_id = models.CharField(max_length=200, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.workspace} {self.plan}/{self.cycle} {self.currency} {self.amount} [{self.status}]"


class SalesLead(models.Model):
    """Enterprise / contact-sales enquiries."""

    name = models.CharField(max_length=120)
    email = models.EmailField()
    company = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    message = models.TextField()
    handled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}>"
