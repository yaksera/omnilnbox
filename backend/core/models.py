import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Workspace(models.Model):
    """A tenant. Every channel, contact and conversation belongs to exactly one workspace."""

    PLAN_CHOICES = [
        ("free", "Free"), ("starter", "Starter"), ("pro", "Pro"),
        ("business", "Business"), ("enterprise", "Enterprise"),
    ]
    CYCLE_CHOICES = [("monthly", "Monthly"), ("yearly", "Yearly")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)

    # --- subscription ---
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="free")
    billing_cycle = models.CharField(max_length=10, choices=CYCLE_CHOICES, default="monthly")
    plan_expires_at = models.DateTimeField(null=True, blank=True,
                                           help_text="Paid/trial plan end. After it the workspace falls back to Free.")
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    extra_seats = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="NPR")

    # --- settings ---
    agents_see_all = models.BooleanField(
        default=True, help_text="If false (Business plan), agents only see conversations assigned to them or unassigned."
    )
    unanswered_alert_minutes = models.PositiveIntegerField(
        default=30, help_text="Email the team when a customer waits this long without a reply (0 = off).")
    # Service quality
    sla_minutes = models.PositiveIntegerField(default=60, help_text="First-response target in minutes (0 = off).")
    csat_enabled = models.BooleanField(default=False, help_text="Ask customers to rate the help when a chat is closed.")
    csat_question = models.CharField(max_length=300, blank=True,
                                     default="How did we do? Reply with a number from 1 (bad) to 5 (great) ⭐")
    # White-label (Business+): shown to your team and your customers instead of OmniInbox
    brand_name = models.CharField(max_length=60, blank=True)
    brand_color = models.CharField(max_length=7, blank=True)
    brand_logo = models.ForeignKey("publishing.MediaAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hide_powered_by = models.BooleanField(default=False)
    # Platform admin (you, the OmniInbox owner): a suspended workspace can't use the app, and its channels,
    # widget and payment links stop working until it is reactivated.
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspended_reason = models.CharField(max_length=300, blank=True)
    is_internal = models.BooleanField(default=False, help_text="Your own workspace (e.g. the website chat): not a customer.")
    # Renewal reminder emails already sent for the current period: {"<plan_expires_at iso>": ["7", "3", "1", "expired"]}
    renewal_reminders = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:120] or "workspace"
            slug, i = base, 1
            while Workspace.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    # --- plan helpers ---
    @property
    def is_expired(self):
        return self.plan != "free" and self.plan_expires_at is not None and timezone.now() >= self.plan_expires_at

    @property
    def effective_plan(self):
        """The plan whose limits apply right now (Free once a paid plan/trial has lapsed)."""
        return "free" if self.is_expired else self.plan

    @property
    def is_trialing(self):
        return bool(self.trial_ends_at and timezone.now() < self.trial_ends_at and not self.is_expired
                    and self.plan_expires_at == self.trial_ends_at)

    @property
    def plan_info(self):
        from billing.plans import get_plan
        return get_plan(self.effective_plan)

    @property
    def channel_limit(self):
        return self.plan_info["channels"]

    @property
    def seat_limit(self):
        extra = self.extra_seats if self.effective_plan != "free" else 0
        return self.plan_info["seats"] + extra

    @property
    def is_suspended(self):
        return self.suspended_at is not None

    def has_feature(self, key):
        return key in self.plan_info["features"]

    def start_trial(self):
        from billing.plans import TRIAL_DAYS, TRIAL_PLAN
        self.plan = TRIAL_PLAN
        self.trial_ends_at = timezone.now() + timedelta(days=TRIAL_DAYS)
        self.plan_expires_at = self.trial_ends_at

    def __str__(self):
        return self.name


class Membership(models.Model):
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_SUPERVISOR = "supervisor"
    ROLE_AGENT = "agent"
    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"), (ROLE_ADMIN, "Admin"),
        (ROLE_SUPERVISOR, "Supervisor"), (ROLE_AGENT, "Agent"),
    ]
    RANK = {ROLE_OWNER: 4, ROLE_ADMIN: 3, ROLE_SUPERVISOR: 2, ROLE_AGENT: 1}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_AGENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "workspace")

    @property
    def rank(self):
        return self.RANK.get(self.role, 0)

    def __str__(self):
        return f"{self.user} @ {self.workspace} ({self.role})"


def _invite_token():
    return secrets.token_urlsafe(32)


def _invite_expiry():
    return timezone.now() + timedelta(days=7)


class Invitation(models.Model):
    """Invite link for a new team member. The token is only ever shown to admins / emailed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Membership.ROLE_CHOICES, default=Membership.ROLE_AGENT)
    token = models.CharField(max_length=64, unique=True, default=_invite_token, editable=False)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    expires_at = models.DateTimeField(default=_invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_valid(self):
        return self.accepted_at is None and timezone.now() < self.expires_at

    @property
    def url(self):
        return f"{settings.FRONTEND_URL}/invite/{self.token}"
