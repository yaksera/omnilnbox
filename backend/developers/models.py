import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models

EVENTS = {
    "message.received": "A customer sent a message",
    "message.sent": "Your team (or automation) replied",
    "conversation.closed": "A conversation was closed",
    "order.created": "An order was created",
    "order.paid": "An order was paid",
    "order.status_changed": "An order's status changed",
    "csat.received": "A customer rated your help",
}


def new_secret():
    return secrets.token_hex(24)


def hash_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=16, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def issue(cls, workspace, user, name):
        raw = f"omni_{secrets.token_urlsafe(32)}"
        key = cls.objects.create(workspace=workspace, created_by=user, name=name, prefix=raw[:12], key_hash=hash_key(raw))
        return key, raw


class WebhookEndpoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="webhook_endpoints")
    url = models.URLField(max_length=500)
    events = models.JSONField(default=list)
    secret = models.CharField(max_length=64, default=new_secret)
    active = models.BooleanField(default=True)
    failures = models.PositiveIntegerField(default=0)
    last_status = models.IntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class WebhookDelivery(models.Model):
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    status_code = models.IntegerField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
