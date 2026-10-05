"""Per-user security and notification settings, push subscriptions and the workspace activity log."""
from django.conf import settings
from django.db import models

from core.crypto import EncryptedJSONField


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    email_verified = models.BooleanField(default=False)
    # Two-factor login (TOTP, e.g. Google Authenticator). Secrets are encrypted at rest.
    two_factor = EncryptedJSONField(blank=True, default=dict)  # {"secret", "pending", "recovery": [sha256...]}
    two_factor_enabled = models.BooleanField(default=False)
    # Notifications
    notify_email_unanswered = models.BooleanField(default=True)
    onboarding_dismissed = models.BooleanField(default=False)
    language = models.CharField(max_length=5, default="en", choices=[("en", "English"), ("ne", "नेपाली")])
    # "Log out of all devices" / password reset: access tokens issued before this moment are rejected.
    sessions_revoked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def of(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj

    def __str__(self):
        return f"Profile of {self.user}"


class PushSubscription(models.Model):
    """A browser/phone that asked for push notifications (Web Push API)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)


class ServerKey(models.Model):
    """Server-generated keys (e.g. the VAPID key pair for Web Push)."""

    name = models.CharField(max_length=40, unique=True)
    value = EncryptedJSONField(default=dict)


class AuditLog(models.Model):
    workspace = models.ForeignKey("core.Workspace", null=True, blank=True, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_label = models.CharField(max_length=200, blank=True)  # kept if the user is deleted
    action = models.CharField(max_length=60, db_index=True)
    target = models.CharField(max_length=300, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "-created_at"], name="audit_ws_recent")]

    def __str__(self):
        return f"{self.action} by {self.actor_label}"
