"""Social publishing: connected accounts, uploaded media, posts and their per-platform targets."""
import uuid

from django.conf import settings
from django.db import models

from core.crypto import EncryptedJSONField

PLATFORMS = [("facebook", "Facebook Page"), ("instagram", "Instagram"), ("youtube", "YouTube"), ("tiktok", "TikTok")]


class SocialAccount(models.Model):
    """A Page / profile / channel we can publish to. Tokens are encrypted at rest."""

    STATUS_ACTIVE, STATUS_ERROR = "active", "error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="social_accounts")
    platform = models.CharField(max_length=20, choices=PLATFORMS)
    external_id = models.CharField(max_length=200)  # page id / ig user id / youtube channel id / tiktok open_id
    name = models.CharField(max_length=200)
    avatar_url = models.URLField(max_length=1000, blank=True)
    credentials = EncryptedJSONField(blank=True, default=dict)
    status = models.CharField(max_length=10, default=STATUS_ACTIVE)
    last_error = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("workspace", "platform", "external_id")
        ordering = ["platform", "name"]

    def __str__(self):
        return f"{self.get_platform_display()}: {self.name}"


def _media_path(instance, filename):
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "bin").lower()[:5]
    # Unguessable name; files are never served statically, only through signed, expiring URLs
    return f"publishing/{instance.workspace_id}/{uuid.uuid4().hex}.{ext}"


class MediaAsset(models.Model):
    KIND_IMAGE, KIND_VIDEO = "image", "video"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="media_assets")
    file = models.FileField(upload_to=_media_path)
    kind = models.CharField(max_length=10)
    mime = models.CharField(max_length=50)
    size = models.PositiveBigIntegerField()
    original_name = models.CharField(max_length=255, blank=True)
    # Read with ffmpeg on upload (empty when ffmpeg isn't available)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True, help_text="Seconds (videos)")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class Post(models.Model):
    STATUSES = [
        ("draft", "Draft"), ("scheduled", "Scheduled"), ("publishing", "Publishing"),
        ("published", "Published"), ("partial", "Partly published"), ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="posts")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    caption = models.TextField(max_length=5000, blank=True)
    media = models.ForeignKey(MediaAsset, null=True, blank=True, on_delete=models.SET_NULL, related_name="posts")
    status = models.CharField(max_length=12, choices=STATUSES, default="draft", db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class PostTarget(models.Model):
    """One post on one account. Options hold per-platform settings (YouTube title, privacy...)."""

    STATUSES = [("pending", "Pending"), ("publishing", "Publishing"), ("published", "Published"), ("failed", "Failed")]

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="targets")
    account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE, related_name="targets")
    caption = models.TextField(max_length=5000, blank=True, help_text="Overrides the post caption for this platform")
    options = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    external_id = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("post", "account")
