"""Who a broadcast can reach, and sending it politely (platform rules, opt-outs, rate limits)."""
import logging
import re
import threading
import time
from datetime import timedelta

from django.db import close_old_connections
from django.db.models import Count
from django.utils import timezone

from inbox.models import Conversation, Message

from .models import Broadcast, Recipient

logger = logging.getLogger(__name__)

# Channel → what's allowed
RULES = {
    "whatsapp": {"kinds": ["template"], "window_days": None,
                 "note": "WhatsApp only allows approved message templates for broadcasts (you pay Meta per conversation)."},
    "telegram": {"kinds": ["text"], "window_days": None, "note": "Everyone who started a chat with your bot."},
    "viber": {"kinds": ["text"], "window_days": None, "note": "Subscribers of your Viber bot (Viber may charge per message)."},
    "messenger": {"kinds": ["text"], "window_days": 1,
                  "note": "Meta allows messages only within 24 hours of the customer's last message, so only recent chats are included."},
    "instagram": {"kinds": ["text"], "window_days": 1,
                  "note": "Meta allows messages only within 24 hours of the customer's last message, so only recent chats are included."},
}
STOP_WORDS = {"stop", "unsubscribe", "stop messages", "band gara", "band garnus", "बन्द", "रोक्नुहोस्"}
START_WORDS = {"start", "subscribe"}
DELAY = 0.12  # seconds between messages (stays well under platform rate limits)


def audience(ws, channel, spec):
    rule = RULES.get(channel.provider)
    qs = (Conversation.objects.filter(workspace=ws, channel=channel, contact__opted_out=False)
          .exclude(external_thread_id__startswith="comment:").select_related("contact"))
    tags = [int(t) for t in (spec.get("tags") or []) if str(t).isdigit()]
    if tags:
        qs = qs.filter(tags__id__in=tags).distinct()
    days = spec.get("active_days")
    if rule and rule["window_days"]:
        days = min(int(days or rule["window_days"]), rule["window_days"])
    if days:
        cutoff = timezone.now() - timedelta(days=int(days))
        last_in = Message.objects.filter(conversation__in=qs, direction="in", sent_at__gte=cutoff).values("conversation_id")
        qs = qs.filter(id__in=last_in)
    if spec.get("customers_only"):
        qs = qs.filter(contact__customer__isnull=False)
    return qs


def render(text, conversation):
    first = (conversation.contact.name or "").split(" ")[0] or "there"
    return (text or "").replace("{name}", first).replace("{first_name}", first)


def template_text(body, params):
    return re.sub(r"\{\{(\d+)\}\}", lambda m: params[int(m.group(1)) - 1] if int(m.group(1)) <= len(params) else m.group(0), body or "")


def _send_one(b, rcp, provider):
    conv = rcp.conversation
    if conv.contact.opted_out:
        return "skipped", "Opted out"
    if b.kind == "template":
        params = [render(v, conv) for v in (b.variables or [])]
        text = template_text(b.template_body, params) or f"[Template: {b.template_name}]"
        if hasattr(provider, "send_template"):
            ext = provider.send_template(conv, b.template_name, b.template_language, params)
        else:  # demo channel
            ext = provider.send(conv, text)
    else:
        text = render(b.text, conv)
        ext = provider.send(conv, text)
    Message.objects.create(conversation=conv, direction="out", bot="broadcast", sender_name=f"Broadcast: {b.name}"[:255],
                           sent_by=b.created_by, text=text, external_id=ext or "", status="sent", sent_at=timezone.now())
    Conversation.objects.filter(pk=conv.pk).update(last_message_at=timezone.now(), last_message_preview=text[:300])
    return "sent", ""


def send_batch(broadcast_id, limit=200):
    """Send up to `limit` pending messages. Safe to run from several places: each recipient is claimed once."""
    from integrations.providers import ProviderError, get_provider
    b = Broadcast.objects.select_related("channel", "created_by").get(id=broadcast_id)
    if b.status != "sending":
        return 0
    provider = get_provider(b.channel)
    done = 0
    for rcp in list(b.recipients.filter(status="pending").select_related("conversation__contact")[:limit]):
        if Recipient.objects.filter(pk=rcp.pk, status="pending").update(status="sending") != 1:
            continue  # someone else took it
        try:
            status, error = _send_one(b, rcp, provider)
        except ProviderError as exc:
            status, error = "failed", str(exc)[:500]
        except Exception as exc:  # noqa: BLE001
            logger.exception("Broadcast send failed")
            status, error = "failed", f"Unexpected error: {type(exc).__name__}"
        Recipient.objects.filter(pk=rcp.pk).update(status=status, error=error, sent_at=timezone.now())
        done += 1
        if DELAY:
            time.sleep(DELAY)
        if Broadcast.objects.filter(pk=b.pk, status="cancelled").exists():
            break
    refresh_counts(b)
    return done


def refresh_counts(b):
    b.refresh_from_db()
    rows = dict(b.recipients.values_list("status").annotate(n=Count("id")).order_by())
    b.sent, b.failed = rows.get("sent", 0), rows.get("failed", 0)
    if b.status == "sending" and not rows.get("pending") and not rows.get("sending"):
        b.status, b.finished_at = "done", timezone.now()
    b.save(update_fields=["sent", "failed", "status", "finished_at"])


def start(b):
    conv_ids = list(audience(b.workspace, b.channel, b.audience).values_list("id", flat=True))
    Recipient.objects.bulk_create([Recipient(broadcast=b, conversation_id=c) for c in conv_ids], ignore_conflicts=True)
    b.total, b.status, b.started_at = len(conv_ids), "sending", timezone.now()
    b.save(update_fields=["total", "status", "started_at"])
    from django.db import transaction
    transaction.on_commit(lambda: threading.Thread(target=_run, args=(b.id,), daemon=True).start())
    return b


def _run(broadcast_id):
    close_old_connections()
    try:
        while send_batch(broadcast_id, limit=50):
            pass
    except Exception:  # noqa: BLE001
        logger.exception("Broadcast %s stopped; the worker will resume it", broadcast_id)
    finally:
        close_old_connections()


def resume_all():
    """Worker: continue broadcasts interrupted by a restart."""
    total = 0
    for b in Broadcast.objects.filter(status="sending"):
        Recipient.objects.filter(broadcast=b, status="sending", sent_at__isnull=True).update(status="pending")
        total += send_batch(b.id, limit=200)
    return total


def handle_opt_out(conversation, text):
    """STOP / START replies. Returns a confirmation text, or None if the message isn't a keyword."""
    t = " ".join((text or "").lower().split()).strip(" .!")
    contact = conversation.contact
    if t in STOP_WORDS and not contact.opted_out:
        contact.opted_out = True
        contact.save(update_fields=["opted_out"])
        return "You won't receive offers from us anymore. Reply START to subscribe again. You can still message us anytime."
    if t in START_WORDS and contact.opted_out:
        contact.opted_out = False
        contact.save(update_fields=["opted_out"])
        return "You're subscribed again. Thanks! 🙏"
    return None
