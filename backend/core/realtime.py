"""Instant updates for the web app (long-polling).

Whenever something in a workspace changes (a message arrives or is sent, a conversation is assigned, a file
finishes downloading), `bump(workspace_id)` increases a counter. The browser keeps one request open to
/api/events/ and gets an answer the moment the counter moves, then reloads what it shows.

The counter lives in the cache (instant within one server process). The background worker is a separate
process, so we also compare the newest conversation activity in the database every couple of seconds.
In production use a shared cache (Redis) so every process sees every bump immediately.
"""
import time

from django.core.cache import cache
from django.db import transaction
from django.db.models import Max

WAIT_SECONDS = 20
TICK = 0.35
DB_EVERY = 2.0


def _key(workspace_id):
    return f"omni:rt:{workspace_id}"


def bump(workspace_id):
    if not workspace_id:
        return

    def _do():
        key = _key(workspace_id)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, int(time.time() * 1000) % 10**9, None)
    transaction.on_commit(_do)


def _cache_version(workspace_id):
    v = cache.get(_key(workspace_id))
    if v is None:
        v = int(time.time() * 1000) % 10**9
        cache.add(_key(workspace_id), v, None)
        v = cache.get(_key(workspace_id), v)
    return str(v)


def _db_stamp(workspace_id):
    from inbox.models import Conversation
    latest = Conversation.objects.filter(workspace_id=workspace_id).aggregate(m=Max("last_message_at"))["m"]
    return latest.isoformat() if latest else "0"


def current(workspace_id):
    return f"{_cache_version(workspace_id)}|{_db_stamp(workspace_id)}"


def wait(workspace_id, since, timeout=WAIT_SECONDS):
    """Block until the workspace changes after `since` (a value from current()), or the timeout passes."""
    now_v = current(workspace_id)
    if not since:
        return now_v, False  # first call: just hand out the current version
    if since != now_v:
        return now_v, True  # changed while the browser was busy reloading
    since_cache, _, since_db = since.partition("|")
    deadline, next_db = time.monotonic() + timeout, time.monotonic() + DB_EVERY
    while time.monotonic() < deadline:
        time.sleep(TICK)
        v = _cache_version(workspace_id)
        if v != since_cache:
            return f"{v}|{_db_stamp(workspace_id)}", True
        if time.monotonic() >= next_db:
            next_db = time.monotonic() + DB_EVERY
            stamp = _db_stamp(workspace_id)
            if stamp != since_db:
                return f"{v}|{stamp}", True
    return f"{_cache_version(workspace_id)}|{since_db}", False
