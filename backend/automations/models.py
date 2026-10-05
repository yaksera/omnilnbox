"""AI assistant settings, knowledge base, AI credit usage and automation rules."""
import uuid
from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def default_hours():
    # Nepal: Saturday is the weekly holiday
    return {d: {"on": d != "sat", "start": "10:00", "end": "18:00"} for d in DAYS}


class AssistantSettings(models.Model):
    BOT_OFF, BOT_AFTER_HOURS, BOT_ALWAYS = "off", "after_hours", "always"
    BOT_CHOICES = [(BOT_OFF, "Off"), (BOT_AFTER_HOURS, "Outside business hours"), (BOT_ALWAYS, "Always (24/7)")]
    TONES = [("friendly", "Friendly"), ("professional", "Professional"), ("casual", "Casual")]

    workspace = models.OneToOneField("core.Workspace", on_delete=models.CASCADE, related_name="assistant")
    business_name = models.CharField(max_length=120, blank=True)
    about = models.TextField(max_length=3000, blank=True, help_text="What the business sells, where, delivery, payment...")
    tone = models.CharField(max_length=20, choices=TONES, default="friendly")
    bot_name = models.CharField(max_length=40, default="Assistant")
    bot_mode = models.CharField(max_length=20, choices=BOT_CHOICES, default=BOT_OFF)
    handoff_message = models.CharField(max_length=500, blank=True,
                                       default="Thanks for your patience! A team member will reply to you shortly.")
    auto_tag = models.BooleanField(default=False, help_text="Label new conversations (order, complaint, lead, ...)")
    timezone = models.CharField(max_length=64, default="Asia/Kathmandu")
    hours = models.JSONField(default=default_hours)
    # AI sales staff
    sales_orders = models.BooleanField(default=False, help_text="AI recommends products and takes orders in chat")
    sales_bookings = models.BooleanField(default=False, help_text="AI books visits / appointments")
    booking_label = models.CharField(max_length=60, default="Visit", help_text="e.g. Counselling session, Campus visit")
    booking_minutes = models.PositiveSmallIntegerField(default=30)
    booking_capacity = models.PositiveSmallIntegerField(default=2, help_text="Visits at the same time")
    followup_enabled = models.BooleanField(default=False, help_text="Nudge interested customers who go quiet")
    followup_hours = models.PositiveSmallIntegerField(default=3)
    voice_notes = models.BooleanField(default=True, help_text="Transcribe voice messages so the AI and team can read them")
    check_payments = models.BooleanField(default=True, help_text="Read payment screenshots and match them to orders")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def for_workspace(cls, ws):
        obj, _ = cls.objects.get_or_create(workspace=ws, defaults={"business_name": ws.name[:120]})
        return obj

    def is_open(self, at=None):
        """True during business hours in the workspace's time zone."""
        from zoneinfo import ZoneInfo
        try:
            tz = ZoneInfo(self.timezone)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("Asia/Kathmandu")
        now = (at or timezone.now()).astimezone(tz)
        day = (self.hours or {}).get(DAYS[now.weekday()]) or {}
        if not day.get("on"):
            return False
        try:
            start = datetime.strptime(day.get("start", "00:00"), "%H:%M").time()
            end = datetime.strptime(day.get("end", "23:59"), "%H:%M").time()
        except ValueError:
            return True
        t = now.time()
        return start <= t < end if start <= end else (t >= start or t < end)  # overnight shifts

    def __str__(self):
        return f"Assistant for {self.workspace}"


class KnowledgeSource(models.Model):
    """A document or website the knowledge base was imported from (its entries are KnowledgeItems)."""

    FILE, WEBSITE = "file", "website"
    KINDS = [(FILE, "File"), (WEBSITE, "Website")]
    PROCESSING, READY, FAILED = "processing", "ready", "failed"
    STATUSES = [(PROCESSING, "Processing"), (READY, "Ready"), (FAILED, "Failed")]

    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="knowledge_sources")
    kind = models.CharField(max_length=10, choices=KINDS)
    name = models.CharField(max_length=255, help_text="File name or page title")
    url = models.URLField(max_length=1000, blank=True)
    crawl = models.BooleanField(default=False, help_text="Website: also import linked pages from the same site")
    status = models.CharField(max_length=12, choices=STATUSES, default=PROCESSING)
    error = models.CharField(max_length=500, blank=True)
    pages = models.PositiveIntegerField(default=0, help_text="PDF pages or web pages read")
    chars = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class KnowledgeItem(models.Model):
    """A fact the AI may use: product + price, delivery policy, FAQ answer..."""

    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="knowledge")
    source = models.ForeignKey(KnowledgeSource, null=True, blank=True, on_delete=models.CASCADE, related_name="items",
                               help_text="Empty for entries written by hand")
    title = models.CharField(max_length=200)
    content = models.TextField(max_length=4000)
    # Meaning-based search: the entry's embedding vector (float32 bytes) and the model that made it
    embedding = models.BinaryField(null=True, blank=True, editable=False)
    embedding_model = models.CharField(max_length=100, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class AIUsage(models.Model):
    """AI credits used per workspace per calendar month (1 credit = 1 AI answer/action)."""

    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="ai_usage")
    month = models.DateField()
    credits = models.PositiveIntegerField(default=0)
    tokens = models.PositiveBigIntegerField(default=0)

    class Meta:
        unique_together = ("workspace", "month")


class Rule(models.Model):
    KEYWORD, WELCOME, AWAY, COMMENT = "keyword", "welcome", "away", "comment"
    TRIGGERS = [
        (KEYWORD, "Message contains keywords"), (WELCOME, "First message from a new contact"),
        (AWAY, "Message outside business hours"), (COMMENT, "Comment on a Facebook / Instagram post"),
    ]
    MATCH_CONTAINS, MATCH_EXACT = "contains", "exact"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)
    trigger = models.CharField(max_length=20, choices=TRIGGERS)
    channel = models.ForeignKey("integrations.ChannelAccount", null=True, blank=True, on_delete=models.CASCADE,
                                related_name="rules", help_text="Empty = all channels")
    keywords = models.JSONField(default=list, blank=True)
    match = models.CharField(max_length=10, default=MATCH_CONTAINS,
                             choices=[(MATCH_CONTAINS, "Contains"), (MATCH_EXACT, "Exact message")])
    post_id = models.CharField(max_length=100, blank=True, help_text="Comment rules: only this post (empty = all)")
    reply_text = models.TextField(max_length=2000, blank=True)
    use_ai = models.BooleanField(default=False, help_text="Let the AI write the answer from the knowledge base")
    public_reply_text = models.CharField(max_length=500, blank=True, help_text="Comment rules: public reply under the comment")
    add_tag = models.ForeignKey("inbox.Tag", null=True, blank=True, on_delete=models.SET_NULL)
    assign_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    run_count = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def matches(self, text):
        if self.trigger not in (self.KEYWORD, self.COMMENT):
            return True
        words = [k.strip().lower() for k in (self.keywords or []) if k.strip()]
        if not words:
            return self.trigger == self.COMMENT  # comment rules without keywords answer every comment
        t = " ".join((text or "").lower().split())
        if self.match == self.MATCH_EXACT:
            return t.strip(" ?!.") in words
        return any(w in t for w in words)

    def __str__(self):
        return self.name


class ProcessedComment(models.Model):
    """Comments we've already seen, so a comment is never answered twice."""

    channel = models.ForeignKey("integrations.ChannelAccount", on_delete=models.CASCADE, related_name="+")
    comment_id = models.CharField(max_length=100)
    rule = models.ForeignKey(Rule, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("channel", "comment_id")


class FollowUp(models.Model):
    """A planned nudge to a customer who showed interest and then went quiet. Cancelled when anyone writes first."""

    PENDING, SENT, CANCELLED, SKIPPED = "pending", "sent", "cancelled", "skipped"
    conversation = models.ForeignKey("inbox.Conversation", on_delete=models.CASCADE, related_name="followups")
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="followups")
    reason = models.CharField(max_length=300, blank=True, help_text="What the customer was interested in")
    due_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=10, default=PENDING, db_index=True)
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at"]
