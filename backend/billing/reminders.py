"""Renewal reminder emails: plans are prepaid and never renew automatically, so we remind owners
7, 3 and 1 day(s) before the plan (or free trial) ends, and once when it has ended.
Called by the worker every cycle; each email is sent once per billing period (Workspace.renewal_reminders).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.mail import send
from core.models import Membership, Workspace

from .plans import PLANS

logger = logging.getLogger(__name__)

STAGES = [("7", timedelta(days=7)), ("3", timedelta(days=3)), ("1", timedelta(days=1))]


def _stage(ws, now):
    """Which reminder is due now (or None). Only the most urgent unsent one is sent."""
    left = ws.plan_expires_at - now
    if left <= timedelta(0):
        return "expired" if left > -timedelta(days=3) else None  # don't email about plans that ended long ago
    due = [key for key, window in STAGES if left <= window]
    return due[-1] if due else None


def _email(ws, stage):
    plan = PLANS.get(ws.plan, {}).get("name", ws.plan)
    trial = ws.is_trialing or (stage == "expired" and ws.trial_ends_at)
    what = f"your free {plan} trial" if trial else f"your {plan} plan"
    when = ws.plan_expires_at.strftime("%d %b %Y")
    if stage == "expired":
        subject = f"{ws.name}: {what} has ended"
        lines = [f"{what[0].upper()}{what[1:]} for {ws.name} ended on {when}. The workspace is now on the Free plan, "
                 "so extra channels, the AI chatbot and other paid features are paused.",
                 "Nothing has been deleted. Renew any time and everything switches back on straight away."]
    else:
        days = {"7": "7 days", "3": "3 days", "1": "1 day"}[stage]
        subject = f"{ws.name}: {what} ends in {days}"
        lines = [f"{what[0].upper()}{what[1:]} for {ws.name} ends on {when} ({days} left).",
                 "Plans are prepaid and never renew automatically. Renew now with Khalti, eSewa or card to keep your "
                 "channels, AI chatbot and team connected without interruption."]
    return subject, lines


def send_renewal_reminders(now=None):
    now = now or timezone.now()
    sent = 0
    candidates = Workspace.objects.filter(
        plan_expires_at__isnull=False, suspended_at__isnull=True, is_internal=False,
        plan_expires_at__lte=now + timedelta(days=7), plan_expires_at__gte=now - timedelta(days=3),
    ).exclude(plan="free")
    for ws in candidates:
        stage = _stage(ws, now)
        period = ws.plan_expires_at.isoformat()
        done = (ws.renewal_reminders or {}).get(period, [])
        if not stage or stage in done:
            continue
        owners = list(Membership.objects.filter(workspace=ws, role__in=["owner"]).values_list("user__email", flat=True))
        if not owners:
            continue
        subject, lines = _email(ws, stage)
        button = ("Renew now" if stage != "expired" else "Choose a plan", f"{settings.FRONTEND_URL}/billing")
        with transaction.atomic():
            fresh = Workspace.objects.select_for_update().get(pk=ws.pk)
            reminders = fresh.renewal_reminders or {}
            if stage in reminders.get(period, []):
                continue
            # keep only the current period's record; mark all earlier stages as done too (no late "7 days left")
            order = ["7", "3", "1", "expired"]
            reminders = {period: order[: order.index(stage) + 1]}
            fresh.renewal_reminders = reminders
            fresh.save(update_fields=["renewal_reminders"])
        if send(owners, subject, lines, button):
            sent += 1
        else:
            logger.warning("Renewal reminder for %s could not be emailed", ws.id)
    return sent
