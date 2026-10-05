"""Core inbox logic: storing incoming messages and sending replies through providers."""
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Contact, Conversation, Message

logger = logging.getLogger(__name__)


def _preview(text: str) -> str:
    return " ".join((text or "").split())[:300]


FILE_LABELS = {"image": "📷 Photo", "video": "🎬 Video", "audio": "🎵 Audio", "voice": "🎤 Voice message",
               "sticker": "Sticker", "file": "📎 File"}


def _files_preview(kinds, names=()):
    if not kinds:
        return ""
    first = FILE_LABELS.get(kinds[0], "📎 File")
    if kinds[0] == "file" and names and names[0]:
        first = f"📎 {names[0]}"
    return first if len(kinds) == 1 else f"{first} +{len(kinds) - 1}"


@transaction.atomic
def ingest_message(channel, incoming):
    """Persist an IncomingMessage from a provider. Idempotent on external message id.

    Returns the Message, or None if it was a duplicate.
    """
    contact, created = Contact.objects.get_or_create(
        channel=channel,
        external_id=str(incoming.contact_external_id),
        defaults={
            "workspace": channel.workspace,
            "name": incoming.contact_name or "",
            "handle": incoming.contact_handle or "",
            "avatar_url": incoming.contact_avatar or "",
        },
    )
    if not created:
        changed = False
        if incoming.contact_name and not contact.name:
            contact.name, changed = incoming.contact_name, True
        if incoming.contact_handle and not contact.handle:
            contact.handle, changed = incoming.contact_handle, True
        if changed:
            contact.save()

    conv, _ = Conversation.objects.get_or_create(
        channel=channel,
        external_thread_id=str(incoming.external_thread_id),
        defaults={"workspace": channel.workspace, "contact": contact, "subject": incoming.subject or ""},
    )

    if incoming.external_message_id and conv.messages.filter(external_id=incoming.external_message_id).exists():
        return None

    sent_at = incoming.sent_at or timezone.now()
    try:
        with transaction.atomic():
            msg = Message.objects.create(
                conversation=conv,
                direction=incoming.direction,
                external_id=incoming.external_message_id or "",
                sender_name=incoming.sender_name or incoming.contact_name or "",
                text=incoming.text or "",
                html=incoming.html or "",
                # summary only (email attachments carry raw bytes, which go to inbox.media, not the JSON column)
                attachments=[{k: v for k, v in a.items() if k in ("type", "name", "mime")}
                             for a in (incoming.attachments or []) if isinstance(a, dict)],
                status=Message.STATUS_RECEIVED if incoming.direction == Message.DIRECTION_IN else Message.STATUS_SENT,
                sent_at=sent_at,
            )
    except IntegrityError:
        return None
    if incoming.attachments:
        from . import media
        files = media.create_incoming(msg, incoming.attachments)
        preview_files = _files_preview([f.kind for f in files], [f.name for f in files])
    else:
        preview_files = ""

    if conv.last_message_at is None or sent_at >= conv.last_message_at:
        conv.last_message_at = sent_at
        conv.last_message_preview = _preview(incoming.text or preview_files or incoming.subject)
    if incoming.direction == Message.DIRECTION_IN:
        conv.unread_count += 1
        if conv.status == Conversation.STATUS_CLOSED:
            conv.status = Conversation.STATUS_OPEN  # customer wrote again -> reopen
    if incoming.subject and not conv.subject:
        conv.subject = incoming.subject
    if incoming.thread_meta:
        conv.meta = {**conv.meta, **incoming.thread_meta}
    conv.save()
    if msg.direction == Message.DIRECTION_IN:
        from automations.engine import schedule
        schedule(msg.id)  # auto-replies / AI bot, after commit and off the request thread
        from developers.events import emit, message_data
        emit("message.received", conv.workspace_id, message_data(msg))
    return msg


def add_note(conversation, text, user):
    """Internal note: stored in the thread for teammates, never sent to the customer."""
    return Message.objects.create(
        conversation=conversation, direction=Message.DIRECTION_OUT, is_note=True,
        sender_name=user.get_full_name() or user.email, sent_by=user, text=text,
        status=Message.STATUS_SENT, sent_at=timezone.now(),
    )


def send_reply(conversation, text, user=None, bot="", files=None):
    """Create an outgoing message and deliver it through the channel's provider.

    bot="ai" / "rule" marks automatic replies (AI assistant / automation rule).
    files: uploaded inbox.Attachment objects (photos, voice notes, documents) to send with the text.
    """
    files = list(files or [])
    from integrations.providers import get_provider

    if bot:
        from automations.models import AssistantSettings
        name = AssistantSettings.for_workspace(conversation.workspace).bot_name if bot == "ai" else "Automation"
    else:
        name = (user.get_full_name() or user.email) if user else ""
    msg = Message.objects.create(
        conversation=conversation,
        direction=Message.DIRECTION_OUT,
        bot=bot,
        sender_name=name,
        sent_by=user,
        text=text,
        status=Message.STATUS_PENDING,
        sent_at=timezone.now(),
        attachments=[{"type": f.kind, "name": f.name, "mime": f.mime} for f in files],
    )
    for f in files:
        f.message = msg
        f.save(update_fields=["message"])
    provider = get_provider(conversation.channel)
    try:
        external_id = provider.send_media(conversation, files, text) if files else provider.send(conversation, text)
        msg.external_id = external_id or ""
        msg.status = Message.STATUS_SENT
    except Exception as exc:  # noqa: BLE001 - surface any provider error to the agent
        logger.exception("Sending via %s failed", conversation.channel.provider)
        msg.status = Message.STATUS_FAILED
        msg.error = str(exc)[:2000]
    msg.save()

    conversation.last_message_at = msg.sent_at
    conversation.last_message_preview = _preview(text or _files_preview([f.kind for f in files], [f.name for f in files]))
    fields = ["last_message_at", "last_message_preview"]
    if not bot:
        conversation.unread_count = 0  # a person answered, so they've read it; bot replies leave it unread
        fields.append("unread_count")
    if msg.status == Message.STATUS_SENT and conversation.first_response_at is None and not bot:
        conversation.first_response_at = msg.sent_at  # for "first response time" analytics
        fields.append("first_response_at")
    conversation.save(update_fields=fields)

    if msg.status == Message.STATUS_SENT:
        from developers.events import emit, message_data
        emit("message.sent", conversation.workspace_id, message_data(msg))

    # Demo channels simulate a customer answering back (not to automatic replies: no endless loops)
    if msg.status == Message.STATUS_SENT and not bot and hasattr(provider, "after_send"):
        provider.after_send(conversation, text)
    return msg


# ------------------------------------------------------------------ satisfaction survey (CSAT)
import re as _re

STARS = "⭐"


def send_csat_survey(conversation, user=None):
    """Ask for a 1-5 rating after a human-handled conversation is closed (if the workspace turned it on)."""
    ws = conversation.workspace
    from billing.plans import F_CSAT
    if not (ws.csat_enabled and ws.has_feature(F_CSAT)) or conversation.meta.get("kind") == "comment":
        return None
    if conversation.channel.provider in ("gmail", "outlook", "zoho", "imap"):
        return None  # a rating request by email looks like spam; chat channels only
    if not conversation.messages.filter(direction=Message.DIRECTION_OUT, sent_by__isnull=False, is_note=False).exists():
        return None  # no person answered: nothing to rate
    agent_id = conversation.assigned_to_id or conversation.messages.filter(
        direction=Message.DIRECTION_OUT, sent_by__isnull=False).order_by("-sent_at").values_list("sent_by_id", flat=True).first()
    msg = send_reply(conversation, ws.csat_question or "How did we do? Reply 1-5 ⭐", bot="rule")
    conversation.refresh_from_db(fields=["meta"])
    conversation.meta = {**conversation.meta, "csat_pending": timezone.now().isoformat(), "csat_agent": agent_id}
    conversation.save(update_fields=["meta"])
    return msg


def parse_rating(text):
    t = (text or "").strip()
    if t.count(STARS) in range(1, 6) and len(t.replace(STARS, "").strip()) < 3:
        return t.count(STARS), ""
    m = _re.match(r"^\s*([1-5])(?:\s*/\s*5)?\b[\s,.!:-]*(.*)$", t, _re.S)
    if m:
        return int(m.group(1)), m.group(2).strip()[:500]
    return None


def record_csat(conversation, message):
    """Called for customer messages while a survey is pending. Returns True if it was a rating."""
    from datetime import datetime, timedelta
    pending = conversation.meta.get("csat_pending")
    if not pending or timezone.now() - datetime.fromisoformat(pending) > timedelta(hours=48):
        return False
    rating = parse_rating(message.text)
    if rating is None:
        return False
    from .models import CsatResponse
    score, comment = rating
    CsatResponse.objects.create(workspace=conversation.workspace, conversation=conversation, score=score, comment=comment,
                                agent_id=conversation.meta.get("csat_agent"))
    conversation.meta = {k: v for k, v in conversation.meta.items() if k not in ("csat_pending", "csat_agent")}
    conversation.status, conversation.unread_count = Conversation.STATUS_CLOSED, 0  # a rating doesn't reopen the chat
    conversation.save(update_fields=["meta", "status", "unread_count"])
    send_reply(conversation, "Thank you for your feedback! 🙏" if score >= 4 else
               "Thank you for telling us. We're sorry it wasn't great; a team member will look into it.", bot="rule")
    from developers.events import emit
    emit("csat.received", conversation.workspace_id, {"conversation_id": str(conversation.id), "score": score, "comment": comment})
    return True
