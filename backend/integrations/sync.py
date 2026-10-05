import logging
from concurrent.futures import ThreadPoolExecutor

from django.db import connection, connections

from django.utils import timezone

from inbox.services import ingest_message

from .models import ChannelAccount
from .providers import ProviderError, get_provider

logger = logging.getLogger(__name__)


def sync_channel(channel: ChannelAccount) -> int:
    """Poll one channel and store new messages. Returns the number of new messages."""
    provider = get_provider(channel)
    if not provider.supports_polling:
        return 0
    try:
        items = provider.poll()
    except ProviderError as exc:
        channel.mark_error(exc)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("Polling %s failed", channel)
        channel.mark_error(exc)
        return 0
    count = sum(1 for item in items if ingest_message(channel, item))
    channel.last_synced_at = timezone.now()
    channel.status = ChannelAccount.STATUS_ACTIVE
    channel.last_error = ""
    # Save state + credentials (poll may have refreshed OAuth tokens / advanced cursors)
    channel.save(update_fields=["state", "last_synced_at", "status", "last_error", "credentials"])
    return count


def _sync_one(channel_id) -> int:
    try:
        channel = ChannelAccount.objects.get(id=channel_id)
        return sync_channel(channel)
    finally:
        connections.close_all()  # each worker thread has its own DB connection


def sync_all(max_workers: int = 8) -> int:
    """Poll every polling-capable channel, several at a time (IMAP/HTTP calls are I/O bound)."""
    qs = (ChannelAccount.objects.filter(is_demo=False, workspace__suspended_at__isnull=True)
          .exclude(status=ChannelAccount.STATUS_DISABLED))
    ids = [c.id for c in qs if get_provider(c).supports_polling]
    if not ids:
        return 0
    if len(ids) == 1 or connection.vendor == "sqlite":
        # SQLite allows a single writer; keep it sequential there
        return sum(sync_channel(ChannelAccount.objects.get(id=i)) for i in ids)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(ids))) as pool:
        return sum(pool.map(_sync_one, ids))
