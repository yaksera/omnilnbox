"""Affiliate API: public click tracking, the affiliate's own dashboard, promo codes on Billing,
and the platform-admin screens for approving affiliates and paying them out."""
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit import audit
from accounts.mail import send
from core.permissions import require
from core.platform import IsPlatformAdmin

from . import services
from .models import Affiliate, Commission, Payout, Referral
from .services import AffiliateError

logger = logging.getLogger(__name__)


def _err(exc):
    return Response({"detail": str(exc)}, status=400)


def _mask(name):
    name = (name or "").strip()
    return (name[:3] + "•••") if len(name) > 3 else (name[:1] + "•••")


def _payout_json(p, admin=False):
    out = {"id": p.id, "amount": str(p.amount), "currency": p.currency, "status": p.status, "method": p.method,
           "reference": p.reference, "note": p.note, "requested_at": p.requested_at, "processed_at": p.processed_at}
    if admin:
        out["details"] = p.details
        out["affiliate"] = {"id": p.affiliate_id, "code": p.affiliate.code, "email": p.affiliate.user.email,
                            "name": p.affiliate.user.get_full_name() or p.affiliate.user.email}
    return out


def _commission_json(c):
    return {"id": c.id, "workspace": _mask(c.payment.workspace.name), "plan": c.payment.plan, "cycle": c.payment.cycle,
            "base_amount": str(c.base_amount), "rate": str(c.rate), "amount": str(c.amount), "currency": c.currency,
            "state": c.state, "available_at": c.available_at, "created_at": c.created_at}


def _affiliate_json(a, private=True):
    out = {"id": a.id, "code": a.code, "link": a.link, "status": a.status, "rate": str(a.commission_rate),
           "admin_note": a.admin_note, "created_at": a.created_at, "approved_at": a.approved_at}
    if private:
        out.update(payout_method=a.payout_method, payout_details=a.payout_details or {}, pitch=a.pitch)
    return out


# ------------------------------------------------------------------ public
class ProgramView(APIView):
    """GET /affiliates/program/ -> commission rate, hold days, minimum payout (home page and /affiliates)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        info = services.program_info()
        info.pop("link_base", None)
        return Response(info)


class CodeCheckView(APIView):
    """GET /affiliates/code/<code>/ -> is this promo code valid? (sign-up and billing forms)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "affiliate"

    def get(self, request, code):
        a = services.find_active(code)
        return Response({"valid": bool(a), "code": a.code if a else services.normalize_code(code),
                         "referrer": (a.user.first_name or "") if a else ""})


class ClickView(APIView):
    """POST /affiliates/click/ {code, landing, referrer}: a visit through a tracking link."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "affiliate"

    def post(self, request):
        a = services.record_click(request.data.get("code"), request, request.data.get("landing", ""),
                                  request.data.get("referrer", ""))
        return Response({"valid": bool(a), "code": a.code if a else ""})


# ------------------------------------------------------------------ affiliate (any logged-in user)
class PayoutDetailsIn(serializers.Serializer):
    account_name = serializers.CharField(max_length=120)
    account_number = serializers.CharField(max_length=60)
    bank_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class ApplyIn(serializers.Serializer):
    code = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    payout_method = serializers.ChoiceField(choices=[m for m, _ in Affiliate.PAYOUT_METHODS])
    payout_details = PayoutDetailsIn()
    pitch = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["payout_method"] == "bank" and not data["payout_details"].get("bank_name"):
            raise serializers.ValidationError({"payout_details": ["Add the bank name."]})
        return data


class MeView(APIView):
    """The signed-in user's affiliate account: apply (POST), dashboard (GET), payout details (PATCH)."""

    def get(self, request):
        a = Affiliate.objects.filter(user=request.user).first()
        data = {"program": services.program_info(), "affiliate": None, "suggested_code": services.suggest_code(request.user)}
        if a is None:
            return Response(data)
        commissions = a.commissions.select_related("payment__workspace").all()[:100]
        data.update({
            "affiliate": _affiliate_json(a),
            "stats": services.stats(a),
            "balances": services.balances(a),
            "commissions": [_commission_json(c) for c in commissions],
            "payouts": [_payout_json(p) for p in a.payouts.all()[:50]],
            "referrals": [{"workspace": _mask(r.workspace.name), "source": r.source, "joined_at": r.created_at,
                           "status": services.workspace_status(r.workspace)}
                          for r in a.referrals.select_related("workspace")[:100]],
        })
        return Response(data)

    def post(self, request):
        if Affiliate.objects.filter(user=request.user).exists():
            return Response({"detail": "You've already applied."}, status=400)
        ser = ApplyIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            code = services.validate_new_code(d["code"]) if d["code"] else services.suggest_code(request.user)
        except AffiliateError as exc:
            return Response({"code": [str(exc)]}, status=400)
        a = Affiliate.objects.create(user=request.user, code=code, commission_rate=services.default_rate(),
                                     payout_method=d["payout_method"], payout_details=dict(d["payout_details"]),
                                     pitch=d["pitch"])
        audit(request, "affiliate.applied", target=code, meta={"email": request.user.email})
        _notify_admins(f"New affiliate application: {code}",
                       [f"{request.user.get_full_name() or request.user.email} ({request.user.email}) applied to the "
                        f"affiliate program with code {code}.", f"How they'll promote: {d['pitch'] or '(not given)'}"])
        return Response({"affiliate": _affiliate_json(a)}, status=201)

    def patch(self, request):
        a = get_object_or_404(Affiliate, user=request.user)
        if "payout_method" in request.data or "payout_details" in request.data:
            ser = ApplyIn(data={"payout_method": request.data.get("payout_method", a.payout_method),
                                "payout_details": request.data.get("payout_details", a.payout_details)})
            ser.is_valid(raise_exception=True)
            a.payout_method = ser.validated_data["payout_method"]
            a.payout_details = dict(ser.validated_data["payout_details"])
        if "code" in request.data:
            if a.status != Affiliate.PENDING:
                return Response({"code": ["Your code can't change after approval (links you've shared would break)."]}, status=400)
            try:
                a.code = services.validate_new_code(request.data["code"], exclude_id=a.id)
            except AffiliateError as exc:
                return Response({"code": [str(exc)]}, status=400)
        if "pitch" in request.data and a.status == Affiliate.PENDING:
            a.pitch = str(request.data["pitch"])[:2000]
        a.save()
        return Response({"affiliate": _affiliate_json(a)})


class PayoutRequestView(APIView):
    def post(self, request):
        a = get_object_or_404(Affiliate, user=request.user)
        try:
            p = services.request_payout(a, request.data.get("currency", "NPR"))
        except AffiliateError as exc:
            return _err(exc)
        audit(request, "affiliate.payout_requested", target=f"{p.currency} {p.amount}", meta={"code": a.code})
        _notify_admins(f"Affiliate payout requested: {p.currency} {p.amount}",
                       [f"{a.code} ({a.user.email}) asked to be paid {p.currency} {p.amount} by {dict(Affiliate.PAYOUT_METHODS).get(p.method, p.method)}.",
                        "Pay them, then mark it paid in Admin → Affiliates."])
        return Response(_payout_json(p), status=201)


# ------------------------------------------------------------------ workspace owner: apply a promo code on Billing
class RedeemView(APIView):
    def post(self, request):
        m = require(request, "manage_billing")
        try:
            r = services.attach_referral(m.workspace, request.data.get("code", ""), source="code")
        except AffiliateError as exc:
            return _err(exc)
        audit(request, "billing.promo_code", target=r.affiliate.code)
        return Response({"code": r.affiliate.code}, status=201)


def referral_for_billing(workspace):
    """Extra fields for GET /billing/."""
    from billing.models import Payment
    r = Referral.objects.select_related("affiliate").filter(workspace=workspace).first()
    return {
        "promo_code": r.affiliate.code if r else None,
        "can_add_promo_code": r is None and not Payment.objects.filter(workspace=workspace, status=Payment.STATUS_PAID).exists(),
    }


# ------------------------------------------------------------------ platform admin
def _notify_admins(subject, lines):
    emails = list(get_user_model().objects.filter(is_staff=True, is_active=True).values_list("email", flat=True))
    if emails:
        send(emails, subject, lines)


class AdminAffiliatesView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        status = request.query_params.get("status") or ""
        q = (request.query_params.get("q") or "").strip()
        qs = Affiliate.objects.select_related("user").annotate(
            signups=Count("referrals", distinct=True),
        )
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(user__email__icontains=q) | Q(user__first_name__icontains=q))
        rows = []
        for a in qs[:200]:
            b = services.balances(a)
            rows.append({**_affiliate_json(a), "email": a.user.email, "name": a.user.get_full_name() or a.user.email,
                         "signups": a.signups, "paying": services.stats(a)["paying"],
                         "lifetime": b["lifetime"],
                         "owed": {c: str(sum(Decimal(b[k][c]) for k in ("holding", "available", "requested")))
                                  for c in services.CURRENCIES}})
        unpaid = Commission.objects.filter(status=Commission.PENDING)
        summary = {
            "pending_applications": Affiliate.objects.filter(status=Affiliate.PENDING).count(),
            "active": Affiliate.objects.filter(status=Affiliate.APPROVED).count(),
            "payouts_requested": Payout.objects.filter(status=Payout.REQUESTED).count(),
            "owed": services._money(unpaid),
            "paid_all_time": services._money(Commission.objects.filter(status=Commission.PAID)),
            "referred_revenue": _referred_revenue(),
        }
        return Response({"summary": summary, "results": rows})


def _referred_revenue():
    out = {c: "0.00" for c in services.CURRENCIES}
    for r in Commission.objects.exclude(status=Commission.VOID).values("currency").annotate(total=Sum("base_amount")):
        out[r["currency"]] = str(services._quantize(r["total"], r["currency"]))
    return out


class AdminActionIn(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject", "suspend", "reactivate", "set_rate"])
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, min_value=0, max_value=90,
                                    help_text="Percent, e.g. 20")


class AdminAffiliateDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, affiliate_id):
        a = get_object_or_404(Affiliate.objects.select_related("user"), id=affiliate_id)
        return Response({
            **_affiliate_json(a), "email": a.user.email, "name": a.user.get_full_name() or a.user.email,
            "stats": services.stats(a), "balances": services.balances(a),
            "referrals": [{"workspace": {"id": str(r.workspace_id), "name": r.workspace.name}, "source": r.source,
                           "joined_at": r.created_at, "status": services.workspace_status(r.workspace)}
                          for r in a.referrals.select_related("workspace")[:200]],
            "commissions": [{**_commission_json(c), "workspace": c.payment.workspace.name}
                            for c in a.commissions.select_related("payment__workspace")[:200]],
            "payouts": [_payout_json(p, admin=True) for p in a.payouts.select_related("affiliate__user")[:50]],
        })

    def post(self, request, affiliate_id):
        a = get_object_or_404(Affiliate.objects.select_related("user"), id=affiliate_id)
        ser = AdminActionIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        action = d["action"]
        if action == "approve" or action == "reactivate":
            a.status, a.admin_note = Affiliate.APPROVED, ""
            a.approved_at = a.approved_at or timezone.now()
        elif action in ("reject", "suspend"):
            a.status = Affiliate.REJECTED if action == "reject" else Affiliate.SUSPENDED
            a.admin_note = d["note"]
        if d.get("rate") is not None:
            a.commission_rate = (d["rate"] / 100).quantize(Decimal("0.0001"))
        elif action == "set_rate":
            return Response({"rate": ["Enter the commission percent."]}, status=400)
        a.save()
        audit(request, f"platform.affiliate_{action}", target=a.code,
              meta={"email": a.user.email, "rate": str(a.commission_rate), "note": d["note"]})
        if action == "approve":
            pct = f"{a.commission_rate * 100:.0f}%"
            send(a.user.email, "You're in: OmniInbox affiliate program",
                 [f"Your affiliate account is approved. You earn {pct} of every payment from businesses you refer, "
                  "for as long as they stay subscribed.",
                  f"Your promo code: {a.code}", f"Your link: {a.link}"],
                 button=("Open your affiliate dashboard", f"{_frontend()}/affiliate"))
        elif action in ("reject", "suspend") and d["note"]:
            send(a.user.email, "Your OmniInbox affiliate account",
                 [f"Your affiliate account was {'not approved' if action == 'reject' else 'suspended'}.", f"Reason: {d['note']}"])
        return self.get(request, affiliate_id)


def _frontend():
    return settings.FRONTEND_URL


class AdminPayoutsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        status = request.query_params.get("status") or ""
        qs = Payout.objects.select_related("affiliate__user")
        if status:
            qs = qs.filter(status=status)
        return Response([_payout_json(p, admin=True) for p in qs[:200]])


class PayoutActionIn(serializers.Serializer):
    action = serializers.ChoiceField(choices=["paid", "reject"])
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class AdminPayoutDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, payout_id):
        p = get_object_or_404(Payout.objects.select_related("affiliate__user"), id=payout_id)
        ser = PayoutActionIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            if d["action"] == "paid":
                if not d["reference"]:
                    return Response({"reference": ["Enter the eSewa / Khalti / bank transaction ID."]}, status=400)
                p = services.mark_payout_paid(p, d["reference"], d["note"])
            else:
                p = services.reject_payout(p, d["note"])
        except AffiliateError as exc:
            return _err(exc)
        audit(request, f"platform.affiliate_payout_{d['action']}", target=f"{p.currency} {p.amount}",
              meta={"code": p.affiliate.code, "reference": p.reference, "note": p.note})
        lines = ([f"We've sent your affiliate payout of {p.currency} {p.amount}.", f"Transaction ID: {p.reference}"]
                 if p.status == Payout.PAID else
                 [f"Your payout request of {p.currency} {p.amount} was not processed.",
                  f"Reason: {p.note or 'please contact support'}", "The amount is back in your available balance."])
        send(p.affiliate.user.email, "Your OmniInbox affiliate payout", lines,
             button=("Open your affiliate dashboard", f"{_frontend()}/affiliate"))
        return Response(_payout_json(Payout.objects.select_related("affiliate__user").get(pk=p.pk), admin=True))
