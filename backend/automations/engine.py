"""Runs automations and the AI bot for each new customer message.

Order: welcome rule -> keyword rules -> AI bot (or away rule) -> AI auto-tagging.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from django.db import close_old_connections, transaction
from django.utils import timezone

from billing.plans import F_AI, F_AI_BOT, F_AUTOMATIONS

from . import ai, llm
from .models import AssistantSettings, Rule

logger = logging.getLogger(__name__)

FRESH_FOR = timedelta(minutes=20)  # never auto-answer old history pulled in by a first sync
LOOP_WINDOW, LOOP_MAX = timedelta(minutes=10), 10# stop if two bots start talking to each other
AWAY_EVERY = timedelta(hours=12)

def _workers():
    from django.conf import settings
    return 1 if settings.DATABASES["default"]["ENGINE"].endswith("sqlite3") else 4  # SQLite: one writer at a time


_pool = ThreadPoolExecutor(max_workers=_workers(), thread_name_prefix="automations")


def schedule(message_id):
    """Called when a customer message is stored. Runs after the DB commit, off the request thread."""
    transaction.on_commit(lambda: _pool.submit(_run, message_id))


def _run(message_id):
    close_old_connections()
    try:
        from accounts.notify import push_incoming
        push_incoming(message_id)  # phone / desktop notifications
    except Exception:  # noqa: BLE001
        logger.exception("Push notification failed for message %s", message_id)
    try:
        process_incoming(message_id)
    except Exception:  # noqa: BLE001
        logger.exception("Automation run failed for message %s", message_id)
    finally:
        close_old_connections()


def render(text, conversation):
    name = (conversation.contact.name or "").split(" ")[0] or "there"
    return (text or "").replace("{name}", name).replace("{first_name}", name).strip()


def _send(conversation, text, bot):
    from inbox.services import send_reply
    return send_reply(conversation, text, bot=bot)


def run_rule(rule, conversation, message=None):
    """Send the rule's reply and apply its tag / assignment."""
    text, ai_sources = "", None
    if rule.use_ai and conversation.workspace.has_feature(F_AI) and llm.configured():
        try:
            answer = ai.bot_answer(conversation)
            text = answer["reply"]
            ai_sources = answer.get("sources")
        except Exception as exc:  # noqa: BLE001 - fall back to the fixed text
            logger.warning("AI answer for rule %s failed: %s", rule.id, exc)
    text = text or render(rule.reply_text, conversation)
    if text:
        msg = _send(conversation, text, "rule")
        if ai_sources:
            _remember_sources(msg, ai_sources)
        rule.last_error = msg.error[:500] if msg.status == "failed" else ""
    if rule.add_tag_id:
        conversation.tags.add(rule.add_tag_id)
    if rule.assign_to_id and not conversation.assigned_to_id:
        if conversation.workspace.memberships.filter(user_id=rule.assign_to_id).exists():
            conversation.assigned_to_id = rule.assign_to_id
            conversation.save(update_fields=["assigned_to"])
    Rule.objects.filter(pk=rule.pk).update(run_count=rule.run_count + 1, last_run_at=timezone.now(),
                                           last_error=rule.last_error)


def _rules(ws, conversation, trigger):
    from django.db.models import Q
    return Rule.objects.filter(workspace=ws, enabled=True, trigger=trigger).filter(
        Q(channel__isnull=True) | Q(channel=conversation.channel_id))


def run_bot(conversation, cfg):
    from . import sales
    answer = ai.bot_answer(conversation)
    text = None
    if not answer["handoff"] and answer.get("action", "none") != "none":
        # The AI wants to take an order / book a visit: checked against real data before anything happens.
        try:
            text = sales.apply(conversation, cfg, answer, lambda feedback: ai.bot_answer(conversation, feedback=feedback))
        except Exception:  # noqa: BLE001 - never leave the customer without an answer
            logger.exception("Sales action failed in conversation %s", conversation.id)
            answer.update(handoff=True, reason="The AI couldn't finish the order / booking", reply="")
    if answer["handoff"]:
        run_bot_handoff(conversation, cfg, answer)
    else:
        text = text or answer["reply"]
        if text:
            _remember_sources(_send(conversation, text, "ai"), answer.get("sources"))
    try:
        sales.plan_followup(conversation, cfg, answer)
    except Exception:  # noqa: BLE001
        logger.exception("Planning a follow-up failed for %s", conversation.id)
    return answer


def run_bot_handoff(conversation, cfg, answer):
    from inbox.models import Message
    conversation.meta = {**conversation.meta, "bot_paused": True, "bot_pause_reason": "handoff",
                         "bot_handoff_reason": answer.get("reason", "")}
    conversation.save(update_fields=["meta"])
    reply = answer.get("reply") or cfg.handoff_message
    if reply:
        _remember_sources(_send(conversation, reply, "ai"), answer.get("sources"))
    Message.objects.create(conversation=conversation, direction="out", is_note=True, bot="ai", sender_name=cfg.bot_name,
                           text=f"AI handed this conversation to the team. Reason: {answer.get('reason') or 'needs a human'}",
                           status="sent", sent_at=timezone.now())
    return answer


def _remember_sources(msg, sources):
    """Show the team which knowledge entries an AI answer came from."""
    if msg is not None and sources:
        from inbox.models import Message
        Message.objects.filter(pk=msg.pk).update(sources=sources)


def _ai_budget_spent(conversation, now):
    """Public website widgets have per-visitor and per-day AI reply budgets (see WebsiteProvider.limits)."""
    channel = conversation.channel
    if channel.provider != "website":
        return False
    from inbox.models import Message
    from integrations.providers.website import WebsiteProvider
    limits = WebsiteProvider.limits(channel.credentials)
    since = now - timedelta(hours=24)
    ai_msgs = Message.objects.filter(bot="ai", direction="out", is_note=False, sent_at__gte=since)
    if ai_msgs.filter(conversation=conversation).count() >= limits["ai_per_visitor"]:
        conversation._limit_reason = f"{limits['ai_per_visitor']} AI replies per visitor per day"
        return True
    if ai_msgs.filter(conversation__channel=channel).count() >= limits["ai_per_day"]:
        conversation._limit_reason = f"{limits['ai_per_day']} AI replies per day on this widget"
        return True
    return False


def _stop_bot_for_limit(conversation, cfg):
    """Budget reached: tell the visitor a person will reply, pause the AI here and leave a note for the team."""
    from inbox.models import Message
    reason = getattr(conversation, "_limit_reason", "AI limit reached")
    conversation.meta = {**conversation.meta, "bot_paused": True, "bot_pause_reason": "limit"}
    conversation.save(update_fields=["meta"])
    _send(conversation, cfg.handoff_message or "Thanks! A member of our team will reply to you here soon.", "rule")
    Message.objects.create(
        conversation=conversation, direction="out", is_note=True, bot="ai", sender_name=cfg.bot_name,
        text=f"AI stopped in this chat: limit reached ({reason}). Please reply to the visitor. "
             "Change the limits in Channels → Website chat → Edit.",
        status="sent", sent_at=timezone.now(),
    )
    logger.info("AI budget reached for conversation %s: %s", conversation.id, reason)


def process_incoming(message_id):
    from inbox.models import Message
    msg = (Message.objects.select_related("conversation__channel", "conversation__contact", "conversation__workspace")
           .filter(id=message_id).first())
    if not msg or msg.direction != "in" or msg.is_note:
        return
    conv, now = msg.conversation, timezone.now()
    ws = conv.workspace
    if ws.suspended_at:
        return
    if conv.meta.get("kind") == "comment":
        return  # public comments are handled by comment-to-DM rules, never by the chat bot
    from inbox.services import record_csat
    if conv.meta.get("csat_pending") and record_csat(conv, msg):
        return
    from broadcasts.services import handle_opt_out
    confirmation = handle_opt_out(conv, msg.text)
    if confirmation:
        _send(conv, confirmation, "rule")
        return
    if now - msg.sent_at > FRESH_FOR:
        return
    # A newer message (ours or theirs) already exists: this one's been dealt with.
    if conv.messages.filter(sent_at__gt=msg.sent_at, is_note=False).exists():
        return
    if conv.messages.filter(bot__in=["ai", "rule"], is_note=False, sent_at__gte=now - LOOP_WINDOW).count() >= LOOP_MAX:
        logger.info("Automation loop guard hit for conversation %s", conv.id)
        return

    cfg = AssistantSettings.for_workspace(ws)
    text = msg.text or ""
    if msg.files.exists() or msg.attachments:
        # Voice notes -> text, photos -> description / payment screenshot check (the AI and the team read these)
        from .media_ai import process_message_files
        found = process_message_files(msg, cfg)
        text = " ".join(x for x in [text, *(a.transcript for a in found["voice"])] if x)
        for att in found["images"]:
            if att.ai_note.get("is_payment"):
                try:
                    from commerce.payment_check import record
                    record(att, conv, att.ai_note)
                except Exception:  # noqa: BLE001
                    logger.exception("Payment screenshot check failed for %s", att.id)
        if found["voice"]:
            from inbox.models import Conversation
            preview = f"🎤 {found['voice'][0].transcript}"[:300]
            Conversation.objects.filter(pk=conv.pk, last_message_at=msg.sent_at).update(last_message_preview=preview)
        # The customer wrote again while we were listening / looking: let the newest message do the answering.
        if conv.messages.filter(direction="in", is_note=False, sent_at__gt=msg.sent_at).exists():
            return
    open_now = cfg.is_open()
    first = not conv.messages.filter(direction="in", is_note=False).exclude(id=msg.id).exists()
    handled = False
    automations = ws.has_feature(F_AUTOMATIONS)

    if automations and first:
        rule = _rules(ws, conv, Rule.WELCOME).first()
        if rule:
            run_rule(rule, conv, msg)

    if automations:
        for rule in _rules(ws, conv, Rule.KEYWORD):
            if rule.matches(text):
                run_rule(rule, conv, msg)
                handled = True
                break

    category = None
    bot_on = (ws.has_feature(F_AI_BOT) and llm.configured() and not conv.meta.get("bot_paused")
              and (cfg.bot_mode == cfg.BOT_ALWAYS or (cfg.bot_mode == cfg.BOT_AFTER_HOURS and not open_now)))
    if not handled and bot_on and _ai_budget_spent(conv, now):
        _stop_bot_for_limit(conv, cfg)
        handled = True
    if not handled and bot_on:
        try:
            answer = run_bot(conv, cfg)
            category = (answer["category"], answer["sentiment"])
            handled = True
        except (llm.AIError, ai.OutOfCredits) as exc:
            logger.warning("AI bot skipped for %s: %s", conv.id, exc)

    if not handled and automations and not open_now:
        rule = _rules(ws, conv, Rule.AWAY).first()
        last = conv.meta.get("away_sent_at")
        if rule and (not last or datetime.fromisoformat(last) + AWAY_EVERY < now):
            run_rule(rule, conv, msg)
            conv.meta = {**conv.meta, "away_sent_at": now.isoformat()}
            conv.save(update_fields=["meta"])

    if cfg.auto_tag and ws.has_feature(F_AI) and llm.configured() and not conv.meta.get("ai_category"):
        try:
            category = category or ai.classify(conv)
            ai.apply_category(conv, *category)
        except (llm.AIError, ai.OutOfCredits) as exc:
            logger.warning("AI tagging skipped for %s: %s", conv.id, exc)
