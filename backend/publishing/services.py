import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import Post, PostTarget
from .platforms.base import PublishError
from .platforms.google_tiktok import TikTokPublisher, YouTubePublisher
from .platforms.meta import FacebookPublisher, InstagramPublisher

logger = logging.getLogger(__name__)

PUBLISHERS = {
    "facebook": FacebookPublisher, "instagram": InstagramPublisher,
    "youtube": YouTubePublisher, "tiktok": TikTokPublisher,
}


def claim(post_id):
    """Atomically move a post from scheduled -> publishing. Returns False if someone else got it."""
    return Post.objects.filter(id=post_id, status="scheduled").update(status="publishing") == 1


def _publish_target(target_id, media_id):
    """Publish one target (runs in its own thread with its own DB connection)."""
    close_old_connections()
    try:
        target = PostTarget.objects.select_related("account", "post").get(id=target_id)
        from .models import MediaAsset
        asset = MediaAsset.objects.filter(id=media_id).first() if media_id else None
        target.status = "publishing"
        target.save(update_fields=["status"])
        try:
            ext_id, url = PUBLISHERS[target.account.platform](target.account).publish(target, asset)
            target.status, target.external_id, target.url = "published", ext_id or "", url or ""
            target.error, target.published_at = "", timezone.now()
            if target.account.status != "active":
                target.account.status, target.account.last_error = "active", ""
                target.account.save(update_fields=["status", "last_error"])
        except PublishError as exc:
            target.status, target.error = "failed", str(exc)[:2000]
            if "token" in str(exc).lower() or "reconnect" in str(exc).lower():
                target.account.status, target.account.last_error = "error", str(exc)[:2000]
                target.account.save(update_fields=["status", "last_error"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Publishing to %s failed", target.account)
            target.status, target.error = "failed", f"Unexpected error ({type(exc).__name__}). Check server logs."
        target.save()
    finally:
        close_old_connections()


def publish_post(post_id):
    """Publish every pending target of a post at the same time and set the post's final status."""
    if not claim(post_id):
        return None
    post = Post.objects.get(id=post_id)
    ids = list(post.targets.filter(status__in=["pending", "failed"]).values_list("id", flat=True))
    if getattr(settings, "BACKGROUND_SYNC", False) or len(ids) <= 1:
        for tid in ids:
            _publish_target(tid, post.media_id)
    else:
        # uploads are slow and network-bound: send to every platform in parallel
        with ThreadPoolExecutor(max_workers=min(4, len(ids)), thread_name_prefix="publish") as pool:
            list(pool.map(lambda tid: _publish_target(tid, post.media_id), ids))
    states = set(post.targets.values_list("status", flat=True))
    post.status = "published" if states == {"published"} else "failed" if "published" not in states else "partial"
    if "published" in states:
        post.published_at = timezone.now()
    post.save(update_fields=["status", "published_at"])
    return post


def publish_in_background(post_id):
    """'Publish now' without making the browser wait for video uploads."""
    def run():
        close_old_connections()
        try:
            publish_post(post_id)
        finally:
            close_old_connections()
    threading.Thread(target=run, daemon=True).start()


def publish_due():
    """Called by the worker: publish every scheduled post whose time has come."""
    due = Post.objects.filter(status="scheduled", scheduled_at__lte=timezone.now()).values_list("id", flat=True)[:20]
    count = 0
    for post_id in list(due):
        if publish_post(post_id):
            count += 1
    return count


@transaction.atomic
def retry_failed(post):
    post.targets.filter(status="failed").update(status="pending", error="")
    post.status, post.scheduled_at = "scheduled", timezone.now()
    post.save(update_fields=["status", "scheduled_at"])


__all__ = ["publish_post", "publish_in_background", "publish_due", "retry_failed", "PostTarget"]
