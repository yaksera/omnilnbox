import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Invitation, Membership
from core.permissions import require
from core.tenancy import get_membership
from integrations.models import ChannelAccount

from affiliates.views import referral_for_billing

from .gateways import GATEWAYS, GatewayError, Stripe, enabled_gateways
from .models import Payment
from .plans import PAID_PLANS, get_plan, price_for, public_catalog

logger = logging.getLogger(__name__)
PERIOD_DAYS = {"monthly": 30, "yearly": 365}


class PlansView(APIView):
    """Public plan catalog used by the pricing page."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(public_catalog())


def _usage(ws):
    now = timezone.now()
    return {
        "channels": ChannelAccount.objects.filter(workspace=ws, is_demo=False).count(),
        "seats": Membership.objects.filter(workspace=ws).count()
        + Invitation.objects.filter(workspace=ws, accepted_at__isnull=True, expires_at__gt=now).count(),
    }


class BillingView(APIView):
    """Current subscription, usage and payment history (owners see payments)."""

    def get(self, request):
        m = get_membership(request)
        ws = m.workspace
        payments = []
        if m.role == Membership.ROLE_OWNER:
            payments = [{
                "id": str(p.id), "plan": p.plan, "cycle": p.cycle, "currency": p.currency, "amount": str(p.amount),
                "gateway": p.gateway, "status": p.status, "created_at": p.created_at, "paid_at": p.paid_at,
                "period_end": p.period_end, "failure_reason": p.failure_reason,
            } for p in ws.payments.all()[:50]]
        return Response({
            "plan": ws.plan, "effective_plan": ws.effective_plan, "plan_name": ws.plan_info["name"],
            "billing_cycle": ws.billing_cycle, "plan_expires_at": ws.plan_expires_at,
            "trial_ends_at": ws.trial_ends_at, "is_trialing": ws.is_trialing, "is_expired": ws.is_expired,
            "extra_seats": ws.extra_seats, "limits": {"channels": ws.channel_limit, "seats": ws.seat_limit},
            "usage": _usage(ws), "features": ws.plan_info["features"],
            "gateways": enabled_gateways(), "payments": payments, "can_manage": m.role == Membership.ROLE_OWNER,
            **referral_for_billing(ws),
        })


class CheckoutView(APIView):
    """POST {plan, cycle, gateway, extra_seats} -> where to send the customer to pay."""

    def post(self, request):
        m = require(request, "manage_billing")
        plan = request.data.get("plan")
        cycle = request.data.get("cycle", "monthly")
        gateway_key = request.data.get("gateway")
        try:
            extra = int(request.data.get("extra_seats", 0))
        except (TypeError, ValueError):
            extra = -1
        if plan not in PAID_PLANS:
            return Response({"plan": ["Choose Starter, Pro or Business. Contact sales for Enterprise."]}, status=400)
        if cycle not in PERIOD_DAYS:
            return Response({"cycle": ["Cycle must be monthly or yearly."]}, status=400)
        if not 0 <= extra <= 100:
            return Response({"extra_seats": ["Must be between 0 and 100."]}, status=400)
        gateway = GATEWAYS.get(gateway_key)
        if gateway is None or not gateway.enabled():
            return Response({"gateway": ["This payment method isn't available."]}, status=400)
        ws = m.workspace
        # Don't let people buy a plan smaller than what they already use
        usage, info = _usage(ws), get_plan(plan)
        if usage["channels"] > info["channels"]:
            return Response({"detail": f"You have {usage['channels']} channels connected; {info['name']} allows "
                                       f"{info['channels']}. Remove channels or choose a bigger plan."}, status=400)
        if usage["seats"] > info["seats"] + extra:
            return Response({"detail": f"You have {usage['seats']} team seats in use; add extra seats or choose a "
                                       "bigger plan."}, status=400)
        payment = Payment.objects.create(
            workspace=ws, created_by=request.user, plan=plan, cycle=cycle, extra_seats=extra,
            currency=gateway.currency, amount=price_for(plan, cycle, gateway.currency, extra), gateway=gateway.key,
        )
        try:
            return Response({"payment_id": str(payment.id), "amount": str(payment.amount),
                             "currency": payment.currency, **gateway.start(payment)})
        except (GatewayError, Exception) as exc:  # noqa: BLE001
            logger.exception("Checkout start failed")
            payment.status, payment.failure_reason = Payment.STATUS_FAILED, str(exc)[:300]
            payment.save(update_fields=["status", "failure_reason"])
            return Response({"detail": "Couldn't start the payment. Please try another method or try again."},
                            status=502)


@transaction.atomic
def activate(payment_id, txn_id="", raw=None):
    """Mark a payment paid and extend the workspace's plan. Idempotent."""
    payment = Payment.objects.select_for_update().select_related("workspace").get(id=payment_id)
    if payment.status == Payment.STATUS_PAID:
        return payment
    ws = payment.workspace
    now = timezone.now()
    # Renewing the same plan stacks on the remaining time; switching plans starts now.
    start = ws.plan_expires_at if (ws.plan == payment.plan and not ws.is_trialing and ws.plan_expires_at
                                   and ws.plan_expires_at > now) else now
    end = start + timedelta(days=PERIOD_DAYS[payment.cycle])
    ws.plan, ws.billing_cycle, ws.extra_seats = payment.plan, payment.cycle, payment.extra_seats
    ws.plan_expires_at, ws.trial_ends_at, ws.currency = end, None, payment.currency
    ws.save()
    payment.status, payment.paid_at = Payment.STATUS_PAID, now
    payment.period_start, payment.period_end = start, end
    payment.gateway_txn_id = txn_id or payment.gateway_txn_id
    payment.raw = raw or payment.raw
    payment.save()
    from accounts.audit import audit
    audit(None, "billing.paid", target=f"{payment.plan} ({payment.cycle})", workspace=ws, actor=payment.created_by,
          meta={"amount": str(payment.amount), "currency": payment.currency, "gateway": payment.gateway})
    from affiliates.services import record_commission
    record_commission(payment)  # recurring affiliate commission, if this workspace was referred
    return payment


def _to_frontend(status, payment=None, message=""):
    q = {"payment": status}
    if message:
        q["message"] = message[:150]
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/billing?{urlencode(q)}")


def payment_return(request, gateway_key, payment_id, failed=False):
    """Browser lands here after paying. We verify with the gateway before activating anything."""
    payment = Payment.objects.filter(id=payment_id, gateway=gateway_key).first()
    gateway = GATEWAYS.get(gateway_key)
    if payment is None or gateway is None:
        return _to_frontend("failed", message="Unknown payment.")
    if payment.status == Payment.STATUS_PAID:
        return _to_frontend("success")
    params = request.GET.dict()
    if failed:
        params["failed"] = "1"
    try:
        ok, txn, raw = gateway.verify(payment, params)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Payment verification error")
        ok, txn, raw = False, "", {"error": str(exc)[:200]}
    if ok:
        activate(payment.id, txn, raw)
        return _to_frontend("success")
    payment.status = Payment.STATUS_FAILED
    payment.failure_reason = str(raw.get("error") or raw.get("status") or "Payment not completed")[:300]
    payment.raw = raw
    payment.save(update_fields=["status", "failure_reason", "raw"])
    return _to_frontend("failed", message="Payment was not completed.")


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Backup activation path in case the customer closes the tab before the redirect."""
    if not Stripe.verify_webhook(request.body, request.headers.get("Stripe-Signature", "")):
        return HttpResponse(status=400)
    import json
    event = json.loads(request.body)
    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        payment = Payment.objects.filter(id=session.get("client_reference_id"), gateway="stripe").first()
        if payment and session.get("payment_status") == "paid" \
                and int(session.get("amount_total", 0)) == int(payment.amount * 100):
            activate(payment.id, session.get("payment_intent") or "", session)
    return HttpResponse(status=200)


class ContactSalesView(APIView):
    """Enterprise enquiries from the pricing page."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        name = str(request.data.get("name", ""))[:120].strip()
        email = str(request.data.get("email", ""))[:200].strip()
        message = str(request.data.get("message", ""))[:3000].strip()
        if not name or "@" not in email or not message:
            return Response({"detail": "Please fill in your name, email and message."}, status=400)
        from .models import SalesLead
        SalesLead.objects.create(name=name, email=email, company=str(request.data.get("company", ""))[:200],
                                 phone=str(request.data.get("phone", ""))[:40], message=message)
        return Response({"ok": True}, status=201)
