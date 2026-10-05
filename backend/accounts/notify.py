"""Who gets told about new customer messages, and how (phone/desktop push, email if nobody answers)."""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from . import mail, webpush
from .models import Profile, PushSubscription

logger = logging.getLogger(__name__)
PUSH_EVERY = 60  # seconds: at most one push per conversation per person per minute


def recipients(conversation):
    """Assigned agent, or everyone who can see unassigned conversations."""
    from core.models import Membership
    if conversation.assigned_to_id:
        return [conversation.assigned_to_id]
    qs = Membership.objects.filter(workspace_id=conversation.workspace_id)
    if not conversation.workspace.agents_see_all:
        qs = qs.exclude(role=Membership.ROLE_AGENT)
    return list(qs.values_list("user_id", flat=True))


def push_incoming(message_id):
    from inbox.models import Message
    msg = (Message.objects.select_related("conversation__contact", "conversation__channel", "conversation__workspace")
           .filter(id=message_id, direction="in", is_note=False).first())
    if not msg or timezone.now() - msg.sent_at > timedelta(minutes=10):
        return 0
    conv = msg.conversation
    users = [u for u in recipients(conv) if cache.add(f"push:{conv.id}:{u}", 1, PUSH_EVERY)]
    if not users:
        return 0
    name = conv.contact.name or conv.contact.handle or "Customer"
    data = {"title": f"{name} · {conv.channel.get_provider_display()}", "body": (msg.text or "New message")[:140],
            "url": f"/inbox?c={conv.id}", "tag": str(conv.id)}
    sent = 0
    for sub in PushSubscription.objects.filter(user_id__in=users):
        if webpush.send(sub, data):
            sent += 1
            PushSubscription.objects.filter(pk=sub.pk).update(last_used_at=timezone.now())
    return sent


def unanswered_alerts():
    """Email a digest when customers have waited longer than the workspace's alert time."""
    from core.models import Membership, Workspace
    from inbox.models import Conversation
    now, sent = timezone.now(), 0
    for ws in Workspace.objects.filter(unanswered_alert_minutes__gt=0):
        cutoff = now - timedelta(minutes=ws.unanswered_alert_minutes)
        convs = [c for c in Conversation.objects.filter(
            workspace=ws, status=Conversation.STATUS_OPEN, unread_count__gt=0, channel__is_demo=False,
            last_message_at__lte=cutoff, last_message_at__gte=now - timedelta(hours=24),
        ).select_related("contact", "channel")[:50] if c.meta.get("alerted_for") != c.last_message_at.isoformat()]
        if not convs:
            continue
        by_user = {}
        managers = list(Membership.objects.filter(workspace=ws).exclude(role=Membership.ROLE_AGENT)
                        .values_list("user_id", flat=True))
        for c in convs:
            for uid in ([c.assigned_to_id] if c.assigned_to_id else managers):
                by_user.setdefault(uid, []).append(c)
        opted_out = set(Profile.objects.filter(user_id__in=by_user, notify_email_unanswered=False)
                        .values_list("user_id", flat=True))
        from django.conf import settings
        from django.contrib.auth import get_user_model
        for user in get_user_model().objects.filter(id__in=set(by_user) - opted_out, is_active=True):
            items = by_user[user.id]
            lines = [f"{len(items)} customer{'s are' if len(items) > 1 else ' is'} waiting for a reply in {ws.name}:"]
            for c in items[:10]:
                mins = int((now - c.last_message_at).total_seconds() // 60)
                lines.append(f"• {c.contact.name or c.contact.handle or 'Customer'} ({c.channel.get_provider_display()}), "
                             f"{mins} min ago: \"{c.last_message_preview[:80]}\"")
            lines.append("You can change or turn off these alerts in Settings → Notifications.")
            if mail.send(user.email, f"{len(items)} customer(s) waiting for a reply", lines,
                         ("Open the inbox", f"{settings.FRONTEND_URL}/inbox")):
                sent += 1
        for c in convs:
            c.meta = {**c.meta, "alerted_for": c.last_message_at.isoformat()}
            c.save(update_fields=["meta"])
    return sent


def subscribed(user):
    return PushSubscription.objects.filter(user=user).exists()


__all__ = ["push_incoming", "unanswered_alerts", "recipients", "subscribed", "Q"]
