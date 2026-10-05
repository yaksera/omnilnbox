"""Affiliate program: people share a promo code or tracking link, and earn a recurring commission on every
payment the workspaces they referred make, for as long as those workspaces stay subscribed.

Flow:  click (/r/CODE) -> sign-up or "Have a promo code?" on Billing -> Referral (one per workspace, forever)
       -> every paid Payment -> Commission (held HOLD_DAYS for refunds) -> affiliate requests a Payout
       -> you pay them by eSewa / Khalti / bank and mark it paid in the admin panel.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.crypto import EncryptedJSONField


def default_commission_rate():
    from decimal import Decimal
    return Decimal(str(settings.AFFILIATE_COMMISSION_RATE))


class Affiliate(models.Model):
    PENDING, APPROVED, REJECTED, SUSPENDED = "pending", "approved", "rejected", "suspended"
    STATUSES = [(PENDING, "Pending review"), (APPROVED, "Approved"), (REJECTED, "Rejected"), (SUSPENDED, "Suspended")]
    PAYOUT_METHODS = [("esewa", "eSewa"), ("khalti", "Khalti"), ("bank", "Bank transfer")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="affiliate")
    code = models.CharField(max_length=20, unique=True, help_text="Promo code, also used in the tracking link /r/CODE")
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING, db_index=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4, default=default_commission_rate,
                                          help_text="Share of every payment, e.g. 0.2000 = 20%")
    payout_method = models.CharField(max_length=10, choices=PAYOUT_METHODS, blank=True)
    # {"account_name": "...", "account_number": "...", "bank_name": "..."} - encrypted at rest
    payout_details = EncryptedJSONField(blank=True, default=dict)
    pitch = models.TextField(blank=True, help_text="How the applicant plans to promote OmniInbox")
    admin_note = models.CharField(max_length=300, blank=True, help_text="Shown to the affiliate when rejected/suspended")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_active(self):
        return self.status == self.APPROVED

    @property
    def link(self):
        return f"{settings.FRONTEND_URL}/r/{self.code}"

    def __str__(self):
        return f"{self.code} ({self.user.email})"


class Referral(models.Model):
    """A workspace brought in by an affiliate. Permanent: the affiliate earns on all its future payments."""

    SOURCES = [("link", "Tracking link"), ("code", "Promo code")]

    workspace = models.OneToOneField("core.Workspace", on_delete=models.CASCADE, related_name="referral")
    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name="referrals")
    source = models.CharField(max_length=4, choices=SOURCES, default="code")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.workspace} <- {self.affiliate.code}"


class Click(models.Model):
    """One visit through a tracking link (for the affiliate's conversion stats)."""

    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name="clicks")
    visitor = models.CharField(max_length=32, blank=True, help_text="Hashed IP + browser, per day (no raw IP stored)")
    landing = models.CharField(max_length=200, blank=True)
    referrer = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class Payout(models.Model):
    REQUESTED, PAID, REJECTED = "requested", "paid", "rejected"
    STATUSES = [(REQUESTED, "Requested"), (PAID, "Paid"), (REJECTED, "Rejected")]

    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name="payouts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=STATUSES, default=REQUESTED, db_index=True)
    method = models.CharField(max_length=10, blank=True)
    details = EncryptedJSONField(blank=True, default=dict, help_text="Snapshot of the payout account when requested")
    reference = models.CharField(max_length=120, blank=True, help_text="Your eSewa / Khalti / bank transaction ID")
    note = models.CharField(max_length=300, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"{self.affiliate.code} {self.currency} {self.amount} [{self.status}]"


class Commission(models.Model):
    """The affiliate's share of one paid subscription payment."""

    PENDING, PAID, VOID = "pending", "paid", "void"
    STATUSES = [(PENDING, "Unpaid"), (PAID, "Paid out"), (VOID, "Void")]

    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name="commissions")
    referral = models.ForeignKey(Referral, null=True, on_delete=models.SET_NULL, related_name="commissions")
    payment = models.OneToOneField("billing.Payment", on_delete=models.CASCADE, related_name="affiliate_commission")
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="What the customer paid")
    rate = models.DecimalField(max_digits=5, decimal_places=4)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING, db_index=True)
    available_at = models.DateTimeField(help_text="Can be paid out from this date (refund window)")
    payout = models.ForeignKey(Payout, null=True, blank=True, on_delete=models.SET_NULL, related_name="commissions")
    void_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def state(self):
        """pending / holding / available / requested / paid / void, as shown to the affiliate."""
        if self.status != self.PENDING:
            return self.status
        if self.payout_id:
            return "requested"
        return "available" if self.available_at <= timezone.now() else "holding"

    def __str__(self):
        return f"{self.affiliate.code} {self.currency} {self.amount} ({self.state})"
