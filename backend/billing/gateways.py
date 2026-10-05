"""Payment gateways: Khalti (ePayment v2), eSewa (ePay v2) and Stripe Checkout.

Every gateway follows the same pattern:
  start(payment)  -> dict telling the frontend where to send the customer
  verify(payment, params) -> (ok: bool, gateway_txn_id, raw) using a server-to-server check

A payment is never activated from redirect parameters alone: we always confirm the amount
and status with the gateway's own API (or a signature made with our secret).
"""
import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal

import requests
from django.conf import settings


class GatewayError(Exception):
    pass


def _return_url(gateway, payment, failed=False, query=""):
    # Payment id lives in the path: eSewa blindly appends "?data=..." to the URL we give it.
    suffix = "failed/" if failed else ""
    return f"{settings.PUBLIC_BASE_URL}/api/billing/return/{gateway}/{payment.id}/{suffix}{query}"


# ----------------------------------------------------------------------------- Khalti
class Khalti:
    key = "khalti"
    currency = "NPR"

    @staticmethod
    def enabled():
        return bool(settings.KHALTI_SECRET_KEY)

    @staticmethod
    def _post(path, body):
        resp = requests.post(f"{settings.KHALTI_BASE_URL}{path}", json=body, timeout=20,
                             headers={"Authorization": f"Key {settings.KHALTI_SECRET_KEY}"})
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text[:300]}
        return resp.status_code, data

    def start(self, payment):
        body = {
            "return_url": _return_url("khalti", payment),
            "website_url": settings.FRONTEND_URL,
            "amount": int(payment.amount * 100),  # paisa
            "purchase_order_id": str(payment.id),
            "purchase_order_name": f"OmniInbox {payment.plan.title()} ({payment.cycle})",
        }
        if payment.created_by:
            body["customer_info"] = {"name": payment.created_by.get_full_name() or payment.created_by.email,
                                     "email": payment.created_by.email}
        code, data = self._post("/epayment/initiate/", body)
        if code >= 400 or not data.get("payment_url"):
            raise GatewayError(f"Khalti: {data}")
        payment.reference = data["pidx"]
        payment.save(update_fields=["reference"])
        return {"redirect_url": data["payment_url"]}

    def verify(self, payment, params):
        pidx = params.get("pidx") or payment.reference
        if pidx != payment.reference:
            return False, "", {"error": "pidx mismatch"}
        _, data = self._post("/epayment/lookup/", {"pidx": pidx})
        ok = data.get("status") == "Completed" and int(data.get("total_amount", 0)) == int(payment.amount * 100)
        return ok, data.get("transaction_id") or "", data


# ----------------------------------------------------------------------------- eSewa
class Esewa:
    key = "esewa"
    currency = "NPR"
    SIGNED = "total_amount,transaction_uuid,product_code"

    @staticmethod
    def enabled():
        return bool(settings.ESEWA_SECRET_KEY and settings.ESEWA_PRODUCT_CODE)

    @staticmethod
    def sign(fields, names):
        msg = ",".join(f"{n}={fields[n]}" for n in names.split(","))
        digest = hmac.new(settings.ESEWA_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def start(self, payment):
        total = str(payment.amount.quantize(Decimal("1")))
        payment.reference = str(payment.id)
        payment.save(update_fields=["reference"])
        fields = {
            "amount": total, "tax_amount": "0", "total_amount": total,
            "transaction_uuid": payment.reference, "product_code": settings.ESEWA_PRODUCT_CODE,
            "product_service_charge": "0", "product_delivery_charge": "0",
            "success_url": _return_url("esewa", payment),
            "failure_url": _return_url("esewa", payment, failed=True),
            "signed_field_names": self.SIGNED,
        }
        fields["signature"] = self.sign(fields, self.SIGNED)
        # eSewa requires a browser form POST, so the frontend auto-submits these fields
        return {"form_url": settings.ESEWA_FORM_URL, "fields": fields}

    def verify(self, payment, params):
        if params.get("failed"):
            return False, "", {"error": "cancelled"}
        try:
            data = json.loads(base64.b64decode(params.get("data", "")))
        except (ValueError, TypeError):
            return False, "", {"error": "bad data"}
        names = data.get("signed_field_names", "")
        try:
            expected = self.sign({k: str(v) for k, v in data.items()}, names)
        except KeyError:
            return False, "", {"error": "missing signed fields"}
        if not hmac.compare_digest(expected, str(data.get("signature", ""))):
            return False, "", {"error": "bad signature"}
        if data.get("transaction_uuid") != payment.reference:
            return False, "", {"error": "reference mismatch"}
        # Double-check with the status API (server to server)
        total = str(payment.amount.quantize(Decimal("1")))
        try:
            status = requests.get(settings.ESEWA_STATUS_URL, timeout=20, params={
                "product_code": settings.ESEWA_PRODUCT_CODE, "total_amount": total,
                "transaction_uuid": payment.reference}).json()
        except (requests.RequestException, ValueError):
            status = {}
        ok = data.get("status") == "COMPLETE" and status.get("status") == "COMPLETE" \
            and Decimal(str(data.get("total_amount", "0")).replace(",", "")) == payment.amount
        return ok, data.get("transaction_code", ""), {"callback": data, "status_api": status}


# ----------------------------------------------------------------------------- Stripe
class Stripe:
    key = "stripe"
    currency = "USD"
    API = "https://api.stripe.com/v1"

    @staticmethod
    def enabled():
        return bool(settings.STRIPE_SECRET_KEY)

    def _call(self, method, path, data=None):
        resp = requests.request(method, f"{self.API}{path}", data=data, timeout=20,
                                auth=(settings.STRIPE_SECRET_KEY, ""))
        body = resp.json()
        if resp.status_code >= 400:
            raise GatewayError(f"Stripe: {body.get('error', {}).get('message', body)}")
        return body

    def start(self, payment):
        cents = int(payment.amount * 100)
        session = self._call("POST", "/checkout/sessions", {
            "mode": "payment",
            "client_reference_id": str(payment.id),
            "customer_email": payment.created_by.email if payment.created_by else None,
            "line_items[0][quantity]": 1,
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": cents,
            "line_items[0][price_data][product_data][name]": f"OmniInbox {payment.plan.title()} ({payment.cycle})",
            "success_url": _return_url("stripe", payment, query="?session_id={CHECKOUT_SESSION_ID}"),
            "cancel_url": _return_url("stripe", payment, failed=True),
            "metadata[payment_id]": str(payment.id),
        })
        payment.reference = session["id"]
        payment.save(update_fields=["reference"])
        return {"redirect_url": session["url"]}

    def verify(self, payment, params):
        if params.get("failed"):
            return False, "", {"error": "cancelled"}
        session = self._call("GET", f"/checkout/sessions/{payment.reference}")
        ok = (session.get("payment_status") == "paid" and session.get("client_reference_id") == str(payment.id)
              and int(session.get("amount_total", 0)) == int(payment.amount * 100))
        return ok, session.get("payment_intent") or "", session

    @staticmethod
    def verify_webhook(payload: bytes, header: str, tolerance=300):
        """Validate the Stripe-Signature header (t=...,v1=...) with the endpoint secret."""
        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            return False
        parts = {}
        for item in header.split(","):
            k, _, v = item.partition("=")
            parts.setdefault(k.strip(), []).append(v.strip())
        try:
            ts = int(parts.get("t", ["0"])[0])
        except ValueError:
            return False
        if abs(time.time() - ts) > tolerance:
            return False
        expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, sig) for sig in parts.get("v1", []))


GATEWAYS = {g.key: g() for g in (Khalti, Esewa, Stripe)}


def enabled_gateways():
    return [{"key": k, "currency": g.currency} for k, g in GATEWAYS.items() if g.enabled()]
