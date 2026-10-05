import secrets
import uuid

from django.conf import settings
from django.db import models

from core.crypto import EncryptedJSONField


class ChannelAccount(models.Model):
    """One connected account on one platform (e.g. a Telegram bot, a Gmail inbox)."""

    PROVIDER_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("messenger", "Messenger"),
        ("instagram", "Instagram"),
        ("tiktok", "TikTok"),
        ("telegram", "Telegram"),
        ("viber", "Viber"),
        ("website", "Website chat"),
        ("discord", "Discord"),
        ("gmail", "Gmail"),
        ("outlook", "Outlook"),
        ("zoho", "Zoho Mail"),
        ("imap", "Other email (IMAP/SMTP)"),
    ]

    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_ERROR = "error"
    STATUS_DISABLED = "disabled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending setup"), (STATUS_ACTIVE, "Active"),
        (STATUS_ERROR, "Error"), (STATUS_DISABLED, "Disabled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="channels")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    name = models.CharField(max_length=120)
    credentials = EncryptedJSONField(blank=True, default=dict)
    # Non-secret provider state: sync cursors, external account ids, ...
    state = models.JSONField(default=dict, blank=True)
    is_demo = models.BooleanField(default=False, help_text="Demo channels use simulated data and never call real APIs.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    last_error = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    webhook_secret = models.CharField(max_length=64, default=secrets.token_urlsafe, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def webhook_url(self):
        return f"{settings.PUBLIC_BASE_URL}/api/webhooks/{self.id}/"

    def mark_error(self, message):
        self.status = self.STATUS_ERROR
        self.last_error = str(message)[:2000]
        self.save(update_fields=["status", "last_error"])

    def mark_active(self):
        self.status = self.STATUS_ACTIVE
        self.last_error = ""
        self.save(update_fields=["status", "last_error"])

    def __str__(self):
        return f"{self.get_provider_display()}: {self.name}"
