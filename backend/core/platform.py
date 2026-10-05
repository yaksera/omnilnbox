"""Platform admin (for you, the OmniInbox owner): every workspace, who's paying, revenue, trials ending,
and suspending accounts. Only users with is_staff=True can call these endpoints
(`python manage.py make_platform_admin you@example.com`).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit import audit
from billing.models import Payment
from billing.plans import PAID_PLANS, PLANS, price_for

from .models import Membership, Workspace


class IsPlatformAdmin(permissions.BasePermission):
    message = "Only OmniInbox platform admins can open this page."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class PlatformView(APIView):
    permission_classes = [IsPlatformAdmin]


def _status(ws, now):
    if ws.is_internal:
        return "internal"
    if ws.suspended_at:
        return "suspended"
    if ws.plan == "free":
        return "free"
    if ws.plan_expires_at and now >= ws.plan_expires_at:
        return "expired"
    if ws.is_trialing:
        return "trial"
    return "paying"


def _mrr(ws):
    """Monthly recurring revenue of one paying workspace (yearly plans count as 1/12 per month)."""
    if ws.plan not in PAID_PLANS or not PLANS[ws.plan].get("price"):
        return Decimal("0")
    if ws.billing_cycle == "yearly":
        return (price_for(ws.plan, "yearly", ws.currency, ws.extra_seats) / 12).quantize(Decimal("0.01"))
    return price_for(ws.plan, "monthly", ws.currency, ws.extra_seats)


def _money(rows):
    """[{currency, total}] -> {"NPR": "1234.00", "USD": "12.00"}"""
    out = {"NPR": "0.00", "USD": "0.00"}
    for r in rows:
        out[r["currency"]] = str((r["total"] or Decimal("0")).quantize(Decimal("0.01")))
    return out


def _paid(qs):
    return _money(qs.values("currency").annotate(total=Sum("amount")))


class OverviewView(PlatformView):
    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        workspaces = list(Workspace.objects.all())
        counts = {"total": len(workspaces), "paying": 0, "trial": 0, "expired": 0, "free": 0, "suspended": 0, "internal": 0}
        mrr = {"NPR": Decimal("0"), "USD": Decimal("0")}
        plans = {}
        trials_ending = 0
        for ws in workspaces:
            st = _status(ws, now)
            counts[st] += 1
            if st == "paying":
                mrr[ws.currency] = mrr.get(ws.currency, Decimal("0")) + _mrr(ws)
                plans[ws.plan] = plans.get(ws.plan, 0) + 1
            if st == "trial" and ws.trial_ends_at and ws.trial_ends_at <= now + timedelta(days=7):
                trials_ending += 1
        paid = Payment.objects.filter(status=Payment.STATUS_PAID)
        signups = (Workspace.objects.filter(created_at__gte=now - timedelta(days=30)).annotate(day=TruncDate("created_at"))
                   .values("day").annotate(n=Count("id")).order_by("day"))
        monthly = (paid.filter(paid_at__gte=(month_start - timedelta(days=330)).replace(day=1))
                   .annotate(month=TruncMonth("paid_at")).values("month", "currency").annotate(total=Sum("amount"))
                   .order_by("month"))
        by_month = {}
        for r in monthly:
            key = r["month"].strftime("%Y-%m")
            by_month.setdefault(key, {"month": key, "NPR": "0.00", "USD": "0.00"})[r["currency"]] = str(r["total"].quantize(Decimal("0.01")))
        return Response({
            "workspaces": counts,
            "trials_ending_7d": trials_ending,
            "users": get_user_model().objects.count(),
            "plans": [{"plan": k, "name": PLANS[k]["name"], "count": v} for k, v in sorted(plans.items())],
            "mrr": {k: str(v.quantize(Decimal("0.01"))) for k, v in mrr.items()},
            "revenue": {
                "this_month": _paid(paid.filter(paid_at__gte=month_start)),
                "last_month": _paid(paid.filter(paid_at__gte=last_month_start, paid_at__lt=month_start)),
                "last_30_days": _paid(paid.filter(paid_at__gte=now - timedelta(days=30))),
                "all_time": _paid(paid),
            },
            "revenue_by_month": list(by_month.values()),
            "signups_by_day": [{"day": r["day"].isoformat(), "count": r["n"]} for r in signups],
            "recent_payments": [_payment_json(p) for p in paid.select_related("workspace").order_by("-paid_at")[:10]],
        })


def _payment_json(p):
    return {"id": str(p.id), "workspace": {"id": str(p.workspace_id), "name": p.workspace.name}, "plan": p.plan,
            "cycle": p.cycle, "currency": p.currency, "amount": str(p.amount), "gateway": p.gateway, "status": p.status,
            "paid_at": p.paid_at, "created_at": p.created_at}


FILTERS = {"all", "paying", "trial", "trial_ending", "expired", "free", "suspended"}


class WorkspacesView(PlatformView):
    def get(self, request):
        now = timezone.now()
        q = (request.query_params.get("q") or "").strip()
        flt = request.query_params.get("filter") or "all"
        qs = Workspace.objects.all()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(memberships__user__email__icontains=q)).distinct()
        if flt == "suspended":
            qs = qs.filter(suspended_at__isnull=False)
        elif flt == "free":
            qs = qs.filter(plan="free", suspended_at__isnull=True)
        elif flt == "expired":
            qs = qs.exclude(plan="free").filter(plan_expires_at__lte=now, suspended_at__isnull=True)
        elif flt in ("trial", "trial_ending"):
            qs = qs.filter(trial_ends_at__gt=now, suspended_at__isnull=True)
            if flt == "trial_ending":
                qs = qs.filter(trial_ends_at__lte=now + timedelta(days=7))
        elif flt == "paying":
            qs = qs.exclude(plan="free").filter(Q(plan_expires_at__gt=now) | Q(plan_expires_at__isnull=True),
                                                trial_ends_at__isnull=True, suspended_at__isnull=True, is_internal=False)
        qs = qs.annotate(
            members=Count("memberships", distinct=True), channel_count=Count("channels", distinct=True),
            last_activity=Max("conversations__last_message_at"),
        ).order_by("-created_at")
        total = qs.count()
        offset = max(0, int(request.query_params.get("offset") or 0))
        rows = list(qs[offset:offset + 50])
        owners = {m.workspace_id: m.user for m in Membership.objects.select_related("user")
                  .filter(workspace__in=rows, role="owner")}
        paid = {(r["workspace_id"], r["currency"]): r["total"] for r in Payment.objects.filter(
            workspace__in=rows, status=Payment.STATUS_PAID).values("workspace_id", "currency").annotate(total=Sum("amount"))}
        out = []
        for ws in rows:
            owner = owners.get(ws.id)
            out.append({
                "id": str(ws.id), "name": ws.name, "slug": ws.slug, "status": _status(ws, now),
                "plan": ws.plan, "plan_name": PLANS.get(ws.plan, {}).get("name", ws.plan), "billing_cycle": ws.billing_cycle,
                "currency": ws.currency, "plan_expires_at": ws.plan_expires_at, "trial_ends_at": ws.trial_ends_at,
                "owner": {"name": owner.get_full_name() or owner.email, "email": owner.email} if owner else None,
                "members": ws.members, "channels": ws.channel_count, "last_activity": ws.last_activity,
                "total_paid": {c: str(Decimal(paid.get((ws.id, c)) or 0).quantize(Decimal("0.01"))) for c in ("NPR", "USD")},
                "mrr": str(_mrr(ws)) if _status(ws, now) == "paying" else "0.00",
                "suspended_at": ws.suspended_at, "suspended_reason": ws.suspended_reason, "created_at": ws.created_at,
            })
        return Response({"count": total, "results": out})


class ActionIn(serializers.Serializer):
    action = serializers.ChoiceField(choices=["suspend", "unsuspend", "extend"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")
    days = serializers.IntegerField(required=False, min_value=1, max_value=3650, default=30)
    plan = serializers.ChoiceField(choices=PAID_PLANS + ["enterprise"], required=False)


class WorkspaceDetailView(PlatformView):
    def get(self, request, ws_id):
        ws = get_object_or_404(Workspace, id=ws_id)
        members = Membership.objects.select_related("user").filter(workspace=ws).order_by("created_at")
        return Response({
            "id": str(ws.id), "name": ws.name, "status": _status(ws, timezone.now()), "plan": ws.plan,
            "plan_expires_at": ws.plan_expires_at, "suspended_reason": ws.suspended_reason,
            "members": [{"name": m.user.get_full_name() or m.user.email, "email": m.user.email, "role": m.role,
                         "last_login": m.user.last_login} for m in members],
            "payments": [_payment_json(p) for p in ws.payments.select_related("workspace").order_by("-created_at")[:50]],
            "usage": {"conversations": ws.conversations.count(),
                      "messages_30d": ws.conversations.filter(messages__sent_at__gte=timezone.now() - timedelta(days=30))
                      .aggregate(n=Count("messages"))["n"] or 0},
        })

    def post(self, request, ws_id):
        ws = get_object_or_404(Workspace, id=ws_id)
        ser = ActionIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d["action"] == "suspend":
            if not d["reason"]:
                return Response({"reason": ["Say why (the workspace's team sees this)."]}, status=400)
            ws.suspended_at, ws.suspended_reason = timezone.now(), d["reason"]
        elif d["action"] == "unsuspend":
            ws.suspended_at, ws.suspended_reason = None, ""
        else:  # extend: gift time or fix a plan by hand (e.g. paid by bank transfer)
            start = max(ws.plan_expires_at or timezone.now(), timezone.now())
            ws.plan = d.get("plan") or (ws.plan if ws.plan != "free" else "starter")
            ws.plan_expires_at, ws.trial_ends_at = start + timedelta(days=d["days"]), None
        ws.save()
        audit(request, f"platform.{d['action']}", target=ws.name, workspace=ws,
              meta={k: str(v) for k, v in d.items() if k != "action"})
        return self.get(request, ws_id)


# ------------------------------------------------------------------ insights: users, AI usage, affiliates, activity
def _since(days):
    return timezone.now() - timedelta(days=days)


def _users_block(now):
    from accounts.models import Profile
    User = get_user_model()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    users = User.objects.all()
    joined = (users.filter(date_joined__gte=now - timedelta(days=30)).annotate(day=TruncDate("date_joined"))
              .values("day").annotate(n=Count("id")).order_by("day"))
    return {
        "total": users.count(),
        "verified": Profile.objects.filter(email_verified=True).count(),
        "two_factor": Profile.objects.filter(two_factor_enabled=True).count(),
        "signups": {"today": users.filter(date_joined__gte=today).count(),
                    "d7": users.filter(date_joined__gte=_since(7)).count(),
                    "d30": users.filter(date_joined__gte=_since(30)).count()},
        "active": {"d1": users.filter(last_login__gte=_since(1)).count(),
                   "d7": users.filter(last_login__gte=_since(7)).count(),
                   "d30": users.filter(last_login__gte=_since(30)).count()},
        "signups_by_day": [{"day": r["day"].isoformat(), "count": r["n"]} for r in joined],
        "recent": [{"name": u.get_full_name() or u.email, "email": u.email, "joined": u.date_joined, "last_login": u.last_login,
                    "workspace": (m.workspace.name if (m := u.memberships.select_related("workspace").first()) else "")}
                   for u in users.order_by("-date_joined")[:8]],
    }


def _ai_block(now):
    from django.conf import settings
    from automations.models import AIUsage
    from inbox.models import Message
    month = timezone.localdate().replace(day=1)
    this_month = AIUsage.objects.filter(month=month)
    totals = this_month.aggregate(credits=Sum("credits"), tokens=Sum("tokens"))
    per_million = Decimal(str(settings.AI_COST_PER_MILLION_TOKENS_USD))

    def cost(tokens):
        return str((Decimal(tokens or 0) / 1_000_000 * per_million).quantize(Decimal("0.01")))

    first = (month - timedelta(days=150)).replace(day=1)
    by_month = (AIUsage.objects.filter(month__gte=first).values("month")
                .annotate(credits=Sum("credits"), tokens=Sum("tokens")).order_by("month"))
    top, near_limit = [], 0
    for row in this_month.select_related("workspace").order_by("-credits")[:200]:
        limit = row.workspace.plan_info.get("ai_credits", 0)
        if limit and row.credits >= limit * 0.9:
            near_limit += 1
        if len(top) < 10:
            top.append({"id": str(row.workspace_id), "name": row.workspace.name, "plan": row.workspace.plan_info["name"],
                        "credits": row.credits, "limit": limit, "tokens": row.tokens, "cost_usd": cost(row.tokens)})
    bot = Message.objects.filter(bot="ai", direction="out", is_note=False)
    return {
        "month": month.isoformat(), "model": settings.OPENROUTER_MODEL, "configured": bool(settings.OPENROUTER_API_KEY),
        "credits": totals["credits"] or 0, "tokens": totals["tokens"] or 0, "cost_usd": cost(totals["tokens"]),
        "cost_per_million_usd": str(per_million),
        "workspaces_using": this_month.filter(credits__gt=0).count(), "near_limit": near_limit,
        "bot_replies": {"d1": bot.filter(sent_at__gte=_since(1)).count(), "d30": bot.filter(sent_at__gte=_since(30)).count()},
        "handoffs_30d": Message.objects.filter(bot="ai", is_note=True, sent_at__gte=_since(30),
                                               text__startswith="AI handed").count(),
        "by_month": [{"month": r["month"].strftime("%Y-%m"), "credits": r["credits"] or 0, "tokens": r["tokens"] or 0,
                      "cost_usd": cost(r["tokens"])} for r in by_month],
        "top": top,
    }


def _affiliates_block(now):
    from affiliates import services as aff
    from affiliates.models import Affiliate, Click, Commission, Payout, Referral
    statuses = dict(Affiliate.objects.values_list("status").annotate(n=Count("id")))
    referrals = list(Referral.objects.select_related("workspace"))
    paying = sum(1 for r in referrals if aff.workspace_status(r.workspace, now) == "subscribed")
    top = []
    for a in Affiliate.objects.select_related("user").annotate(n=Count("referrals")).filter(status="approved").order_by("-n")[:5]:
        top.append({"id": a.id, "code": a.code, "name": a.user.get_full_name() or a.user.email, "signups": a.n,
                    "earned": aff.balances(a)["lifetime"]})
    return {
        "total": sum(statuses.values()), "pending": statuses.get("pending", 0), "approved": statuses.get("approved", 0),
        "suspended": statuses.get("suspended", 0),
        "clicks_30d": Click.objects.filter(created_at__gte=_since(30)).count(),
        "referrals": len(referrals), "referrals_30d": sum(1 for r in referrals if r.created_at >= _since(30)),
        "paying_referrals": paying,
        "payouts_requested": Payout.objects.filter(status=Payout.REQUESTED).count(),
        "owed": aff._money(Commission.objects.filter(status=Commission.PENDING)),
        "paid": aff._money(Commission.objects.filter(status=Commission.PAID)),
        "top": top,
    }


def _activity_block(now):
    from broadcasts.models import Broadcast
    from commerce.models import Order
    from inbox.models import Conversation, Message
    from integrations.models import ChannelAccount
    from publishing.models import Post
    msgs = Message.objects.filter(sent_at__gte=_since(30), is_note=False)
    orders = Order.objects.filter(created_at__gte=_since(30))
    return {
        "messages_30d": {"in": msgs.filter(direction="in").count(), "out": msgs.filter(direction="out").count()},
        "conversations_30d": Conversation.objects.filter(created_at__gte=_since(30)).count(),
        "channels": [{"provider": r["provider"], "count": r["n"]} for r in ChannelAccount.objects.filter(is_demo=False)
                     .values("provider").annotate(n=Count("id")).order_by("-n")],
        "orders_30d": {"count": orders.count(),
                       "value": {r["currency"]: str(r["total"]) for r in orders.values("currency").annotate(total=Sum("total"))}},
        "posts_published_30d": Post.objects.filter(status__in=["published", "partial"], published_at__gte=_since(30)).count(),
        "broadcast_messages_30d": Broadcast.objects.filter(created_at__gte=_since(30)).aggregate(n=Sum("sent"))["n"] or 0,
    }


def _funnel_block(now):
    """Of the workspaces created in the last 90 days: how many trialled, and how many paid."""
    recent = Workspace.objects.filter(created_at__gte=_since(90), is_internal=False)
    total = recent.count()
    paid = recent.filter(payments__status=Payment.STATUS_PAID).distinct().count()
    return {"created_90d": total, "paid_90d": paid, "conversion": round(paid * 100 / total, 1) if total else 0.0}


class InsightsView(PlatformView):
    """Everything at a glance for the platform admin dashboard."""

    def get(self, request):
        now = timezone.now()
        return Response({
            "users": _users_block(now), "ai": _ai_block(now), "affiliates": _affiliates_block(now),
            "activity": _activity_block(now), "funnel": _funnel_block(now),
        })
