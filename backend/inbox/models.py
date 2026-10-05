import uuid

from django.conf import settings
from django.db import models


class Contact(models.Model):
    """A person on the other side of a channel (a Telegram user, an email address, ...)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="contacts")
    channel = models.ForeignKey("integrations.ChannelAccount", on_delete=models.CASCADE, related_name="contacts")
    external_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255, blank=True)
    handle = models.CharField(max_length=255, blank=True, help_text="username, phone number or email")
    avatar_url = models.URLField(max_length=1000, blank=True)
    notes = models.TextField(blank=True)
    # The same person on other channels shares one Customer (orders, address, total spent)
    opted_out = models.BooleanField(default=False, help_text="Replied STOP: never include in broadcasts")
    customer = models.ForeignKey("commerce.Customer", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="contacts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("channel", "external_id")

    def __str__(self):
        return self.name or self.handle or self.external_id


class Conversation(models.Model):
    STATUS_OPEN = "open"
    STATUS_PENDING = "pending"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_PENDING, "Pending"), (STATUS_CLOSED, "Closed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="conversations")
    channel = models.ForeignKey("integrations.ChannelAccount", on_delete=models.CASCADE, related_name="conversations")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="conversations")
    # Provider thread identifier: chat id, PSID, phone number, email thread root, ...
    external_thread_id = models.CharField(max_length=500)
    subject = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_conversations"
    )
    unread_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.CharField(max_length=300, blank=True)
    tags = models.ManyToManyField("Tag", blank=True, related_name="conversations")
    first_response_at = models.DateTimeField(null=True, blank=True)
    # Provider-specific data needed to reply (e.g. email Message-ID to reply to)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("channel", "external_thread_id")
        ordering = ["-last_message_at"]
        indexes = [
            # inbox list: filter by workspace/status, newest first
            models.Index(fields=["workspace", "status", "-last_message_at"], name="conv_ws_status_recent"),
            # unread badges / "Unread" folder
            models.Index(fields=["workspace", "unread_count"], name="conv_ws_unread"),
        ]

    def __str__(self):
        return f"{self.contact} via {self.channel}"


class Message(models.Model):
    DIRECTION_IN = "in"
    DIRECTION_OUT = "out"
    DIRECTION_CHOICES = [(DIRECTION_IN, "Incoming"), (DIRECTION_OUT, "Outgoing")]

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_RECEIVED = "received"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"), (STATUS_SENT, "Sent"),
        (STATUS_RECEIVED, "Received"), (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    external_id = models.CharField(max_length=500, blank=True, db_index=True)
    sender_name = models.CharField(max_length=255, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    text = models.TextField(blank=True)
    html = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECEIVED)
    is_note = models.BooleanField(default=False, help_text="Internal note: visible to the team, never sent.")
    # Who wrote an automatic message: "ai" (AI assistant) or "rule" (automation). Empty for people.
    bot = models.CharField(max_length=10, blank=True, default="")
    # AI answers: the knowledge entries it used, shown to the team ([{"id", "title", "source"}])
    sources = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sent_at", "created_at"]
        indexes = [models.Index(fields=["conversation", "sent_at"], name="msg_conv_sent")]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "external_id"],
                condition=~models.Q(external_id=""),
                name="uniq_message_external_id_per_conversation",
            )
        ]

    def __str__(self):
        return f"[{self.direction}] {self.text[:40]}"


def _attachment_path(instance, filename):
    return f"attachments/{instance.workspace_id}/{instance.id.hex}{instance.extension}"


class Attachment(models.Model):
    """A photo, video, voice note or file in a conversation (received from a customer or sent by the team).

    Files are stored privately and only served through signed, expiring links (see inbox.media).
    """

    IMAGE, VIDEO, AUDIO, VOICE, FILE, STICKER = "image", "video", "audio", "voice", "file", "sticker"
    KINDS = [(k, k.title()) for k in (IMAGE, VIDEO, AUDIO, VOICE, FILE, STICKER)]
    PENDING, READY, FAILED = "pending", "ready", "failed"
    STATUSES = [(PENDING, "Downloading"), (READY, "Ready"), (FAILED, "Failed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="attachments")
    message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.CASCADE, related_name="files")
    kind = models.CharField(max_length=10, choices=KINDS, default=FILE)
    name = models.CharField(max_length=255, blank=True)
    mime = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    extension = models.CharField(max_length=10, blank=True)
    file = models.FileField(upload_to=_attachment_path, blank=True, max_length=300)
    source = models.JSONField(default=dict, blank=True, help_text="How to download it from the platform (id / url).")
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    error = models.CharField(max_length=500, blank=True)
    # AI: what a voice note says, and what a photo shows / whether it's a payment screenshot
    transcript = models.TextField(blank=True)
    ai_note = models.JSONField(default=dict, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="att_status_created")]

    def __str__(self):
        return f"{self.kind}: {self.name or self.id}"


class CsatResponse(models.Model):
    """A customer's 1-5 rating after a conversation was closed."""

    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="csat_responses")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="csat_responses")
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    score = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Tag(models.Model):
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=40)
    color = models.CharField(max_length=7, default="#6366f1")

    class Meta:
        unique_together = ("workspace", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class CannedReply(models.Model):
    """Saved reply. Agents insert it by typing /shortcut in the composer."""

    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="canned_replies")
    shortcut = models.SlugField(max_length=40)
    title = models.CharField(max_length=120)
    body = models.TextField(max_length=4000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("workspace", "shortcut")
        ordering = ["shortcut"]

    def __str__(self):
        return f"/{self.shortcut}"
