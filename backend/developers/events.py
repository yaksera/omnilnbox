"""Outgoing webhooks: emit("order.paid", workspace_id, data) → signed POST to the customer's endpoints.

Signature: X-Omni-Signature: sha256=<hex HMAC-SHA256 of the raw body with the endpoint secret>.
"""
import hashlib
import hmac
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from django.core.serializers.json import DjangoJSONEncoder
from django.db import close_old_connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webhooks")
RETRIES = (0, 5, 30)  # seconds before each attempt
DISABLE_AFTER = 20  # consecutive failed deliveries


def emit(event, workspace_id, data):
    from .models import WebhookEndpoint
    try:
        eps = list(WebhookEndpoint.objects.filter(workspace_id=workspace_id, active=True).values("id", "events"))
    except Exception:  # noqa: BLE001 (e.g. table missing during migrations)
        return
    targets = [e["id"] for e in eps if event in (e["events"] or [])]
    if not targets:
        return
    body = {"id": uuid.uuid4().hex, "event": event, "created_at": timezone.now().isoformat(),
            "workspace_id": str(workspace_id), "data": data}
    payload = json.loads(json.dumps(body, cls=DjangoJSONEncoder))
    for ep_id in targets:
        transaction.on_commit(lambda ep_id=ep_id: _pool.submit(_deliver, ep_id, event, payload))


def sign(secret, raw):
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def deliver_now(endpoint, event, payload, retries=RETRIES):
    """POST with retries. Returns the WebhookDelivery."""
    from core.netguard import UnsafeHostError, assert_public_host
    from .models import WebhookDelivery, WebhookEndpoint
    raw = json.dumps(payload, separators=(",", ":")).encode()
    status, error, attempts, started = None, "", 0, time.monotonic()
    for wait in retries:
        if wait:
            time.sleep(wait)
        attempts += 1
        try:
            u = urlparse(endpoint.url)
            if u.scheme != "https":
                raise UnsafeHostError("Webhook URLs must use https://")
            assert_public_host(u.hostname or "", u.port or 443)
            resp = requests.post(endpoint.url, data=raw, timeout=10, allow_redirects=False, headers={
                "Content-Type": "application/json", "User-Agent": "OmniInbox-Webhooks/1.0",
                "X-Omni-Event": event, "X-Omni-Delivery": payload.get("id", ""), "X-Omni-Signature": sign(endpoint.secret, raw)})
            status, error = resp.status_code, "" if resp.status_code < 300 else resp.text[:200]
            if status < 300:
                break
        except UnsafeHostError as exc:
            status, error = None, str(exc)[:300]
            break
        except requests.RequestException as exc:
            status, error = None, f"{type(exc).__name__}: {str(exc)[:200]}"
    ok = status is not None and status < 300
    d = WebhookDelivery.objects.create(endpoint=endpoint, event=event, payload=payload, status_code=status, error=error,
                                       attempts=attempts, duration_ms=int((time.monotonic() - started) * 1000))
    failures = 0 if ok else endpoint.failures + 1
    WebhookEndpoint.objects.filter(pk=endpoint.pk).update(
        last_status=status, last_error=error, last_delivery_at=timezone.now(), failures=failures,
        **({"active": False} if failures >= DISABLE_AFTER else {}))
    old = list(WebhookDelivery.objects.filter(endpoint=endpoint).values_list("id", flat=True)[50:])
    if old:
        WebhookDelivery.objects.filter(id__in=old).delete()
    return d


def _deliver(ep_id, event, payload):
    close_old_connections()
    try:
        from .models import WebhookEndpoint
        ep = WebhookEndpoint.objects.filter(id=ep_id, active=True).first()
        if ep:
            deliver_now(ep, event, payload)
    except Exception:  # noqa: BLE001
        logger.exception("Webhook delivery failed")
    finally:
        close_old_connections()


# ------------------------------------------------------------------ payload helpers
def message_data(msg):
    conv = msg.conversation
    return {"id": str(msg.id), "direction": msg.direction, "text": msg.text, "sent_at": msg.sent_at, "bot": msg.bot,
            "sender_name": msg.sender_name, "attachments": msg.attachments,
            "conversation": {"id": str(conv.id), "status": conv.status, "subject": conv.subject},
            "channel": {"id": str(conv.channel_id), "provider": conv.channel.provider, "name": conv.channel.name},
            "contact": {"id": str(conv.contact_id), "name": conv.contact.name, "handle": conv.contact.handle}}


def order_data(order):
    from commerce.views import order_json
    return order_json(order)
