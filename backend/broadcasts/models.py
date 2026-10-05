import uuid

from django.conf import settings
from django.db import models


class Broadcast(models.Model):
    STATUSES = [("draft", "Draft"), ("sending", "Sending"), ("done", "Sent"), ("cancelled", "Cancelled")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="broadcasts")
    name = models.CharField(max_length=120)
    channel = models.ForeignKey("integrations.ChannelAccount", on_delete=models.CASCADE, related_name="broadcasts")
    kind = models.CharField(max_length=10, default="text", choices=[("text", "Text"), ("template", "WhatsApp template")])
    text = models.TextField(max_length=4000, blank=True, help_text="{name} = customer's first name")
    template_name = models.CharField(max_length=120, blank=True)
    template_language = models.CharField(max_length=20, blank=True)
    template_body = models.TextField(blank=True, help_text="Template text with {{1}} placeholders (for the inbox copy)")
    variables = models.JSONField(default=list, blank=True, help_text="Values for {{1}}, {{2}}… ({name} allowed)")
    audience = models.JSONField(default=dict, blank=True)  # {"tags": [ids], "active_days": 30, "customers_only": false}
    status = models.CharField(max_length=10, choices=STATUSES, default="draft", db_index=True)
    total = models.PositiveIntegerField(default=0)
    sent = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Recipient(models.Model):
    STATUSES = [("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed"), ("skipped", "Skipped")]

    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="recipients")
    conversation = models.ForeignKey("inbox.Conversation", on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=STATUSES, default="pending", db_index=True)
    error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("broadcast", "conversation")
