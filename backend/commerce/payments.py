"""Payment links paid into the SHOP's own Khalti / eSewa merchant account.

Same rule as OmniInbox billing: an order is only marked paid after a server-to-server check
with the gateway (Khalti lookup API / eSewa signature + status API). Redirect parameters alone
are never trusted.
"""
import base64
import hashlib
import hmac
import json
from decimal import Decimal

import requests
from django.conf import settings

KHALTI_SANDBOX, KHALTI_LIVE = "https://dev.khalti.com/api/v2", "https://khalti.com/api/v2"
ESEWA = {
    False: {"form": "https://rc-epay.esewa.com.np/api/epay/main/v2/form",
            "status": "https://rc.esewa.com.np/api/epay/transaction/status/"},
    True: {"form": "https://epay.esewa.com.np/api/epay/main/v2/form",
           "status": "https://epay.esewa.com.np/api/epay/transaction/status/"},
}
ESEWA_TEST_CODE, ESEWA_TEST_SECRET = "EPAYTEST", "8gBm/:&EnhH.1/q"  # eSewa's public sandbox credentials


class PaymentError(Exception):
    pass


def _return_url(link, gateway, failed=False):
    # The link id is in the path: eSewa appends "?data=..." to whatever URL we give it.
    return f"{settings.PUBLIC_BASE_URL}/api/pay/{link.id}/return/{gateway}/{'failed/' if failed else ''}"


def _paisa(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


class Khalti:
    key = "khalti"

    def __init__(self, shop):
        self.shop = shop
        self.secret = shop.secret("khalti_secret_key")
        self.base = KHALTI_LIVE if shop.khalti_live else KHALTI_SANDBOX

    def enabled(self):
        return bool(self.secret)

    def _post(self, path, body):
        try:
            resp = requests.post(f"{self.base}{path}", json=body, timeout=20,
                                 headers={"Authorization": f"Key {self.secret}"})
        except requests.RequestException as exc:
            raise PaymentError("Couldn't reach Khalti. Try again in a moment.") from exc
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text[:300]}
        return resp.status_code, data

    def start(self, link):
        order = link.order
        body = {
            "return_url": _return_url(link, "khalti"),
            "website_url": settings.FRONTEND_URL,
            "amount": _paisa(link.amount),
            "purchase_order_id": str(link.id),
            "purchase_order_name": f"{order.workspace.name} order {order.number}"[:100],
            "customer_info": {k: v for k, v in {"name": order.recipient_name, "phone": order.recipient_phone}.items() if v},
        }
        code, data = self._post("/epayment/initiate/", body)
        if code >= 400 or not data.get("payment_url"):
            if code == 401:
                raise PaymentError("The shop's Khalti key is invalid. The shop owner needs to check it in Settings → Shop.")
            raise PaymentError(f"Khalti couldn't start the payment: {str(data)[:200]}")
        link.reference, link.gateway = data["pidx"], "khalti"
        link.save(update_fields=["reference", "gateway"])
        return {"redirect_url": data["payment_url"]}

    def verify(self, link, params):
        pidx = params.get("pidx") or link.reference
        if pidx != link.reference:
            return False, "", {"error": "pidx mismatch"}
        _, data = self._post("/epayment/lookup/", {"pidx": pidx})
        ok = data.get("status") == "Completed" and int(data.get("total_amount", 0)) == _paisa(link.amount)
        return ok, data.get("transaction_id") or "", data


class Esewa:
    key = "esewa"
    SIGNED = "total_amount,transaction_uuid,product_code"

    def __init__(self, shop):
        self.shop = shop
        live = shop.esewa_live
        self.code = shop.esewa_merchant_code or ("" if live else ESEWA_TEST_CODE)
        self.secret = shop.secret("esewa_secret_key") or ("" if live else ESEWA_TEST_SECRET)
        self.urls = ESEWA[live]
        self.configured = bool(shop.esewa_merchant_code and shop.secret("esewa_secret_key"))

    def enabled(self):
        return self.configured or (not self.shop.esewa_live and settings.DEBUG)  # sandbox for local testing

    def sign(self, fields, names):
        msg = ",".join(f"{n}={fields[n]}" for n in names.split(","))
        return base64.b64encode(hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()

    def start(self, link):
        total = str(Decimal(link.amount).quantize(Decimal("1")))
        link.reference, link.gateway = f"{link.id}", "esewa"
        link.save(update_fields=["reference", "gateway"])
        fields = {
            "amount": total, "tax_amount": "0", "total_amount": total, "transaction_uuid": link.reference,
            "product_code": self.code, "product_service_charge": "0", "product_delivery_charge": "0",
            "success_url": _return_url(link, "esewa"), "failure_url": _return_url(link, "esewa", failed=True),
            "signed_field_names": self.SIGNED,
        }
        fields["signature"] = self.sign(fields, self.SIGNED)
        return {"form_url": self.urls["form"], "fields": fields}

    def verify(self, link, params):
        if params.get("failed"):
            return False, "", {"error": "cancelled"}
        try:
            data = json.loads(base64.b64decode(params.get("data", "")))
        except (ValueError, TypeError):
            return False, "", {"error": "bad data"}
        try:
            expected = self.sign({k: str(v) for k, v in data.items()}, data.get("signed_field_names", ""))
        except KeyError:
            return False, "", {"error": "missing signed fields"}
        if not hmac.compare_digest(expected, str(data.get("signature", ""))) or data.get("transaction_uuid") != link.reference:
            return False, "", {"error": "bad signature"}
        total = str(Decimal(link.amount).quantize(Decimal("1")))
        try:
            status = requests.get(self.urls["status"], timeout=20, params={
                "product_code": self.code, "total_amount": total, "transaction_uuid": link.reference}).json()
        except (requests.RequestException, ValueError):
            status = {}
        ok = (data.get("status") == "COMPLETE" and status.get("status") == "COMPLETE"
              and Decimal(str(data.get("total_amount", "0")).replace(",", "")) == Decimal(link.amount))
        return ok, data.get("transaction_code", ""), {"callback": data, "status_api": status}


def gateways(shop):
    return {g.key: g for g in (Khalti(shop), Esewa(shop)) if g.enabled()}
