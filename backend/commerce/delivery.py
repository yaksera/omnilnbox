"""Courier integrations.

* Nepal Can Move (NCM): vendor API token ("Authorization: Token <token>"), demo.nepalcanmove.com for testing.
* Pathao: merchant API (OAuth password grant). The base URL is configurable because Pathao runs
  separate deployments per country; confirm yours in the Pathao merchant panel → Developer API.
* Manual: any other courier (Upaya, Aramex, own riders...) with a tracking number/link typed in.
"""
import time
from decimal import Decimal

import requests

NCM_DEMO, NCM_LIVE = "https://demo.nepalcanmove.com", "https://nepalcanmove.com"
RETURNED_WORDS = ("returned", "return to vendor", "rtv")


class DeliveryError(Exception):
    pass


def _json(resp):
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:300]}


class NCM:
    key, label = "ncm", "Nepal Can Move"

    def __init__(self, shop):
        self.shop = shop
        self.token = shop.secret("ncm_token")
        self.base = NCM_LIVE if shop.ncm_live else NCM_DEMO

    def enabled(self):
        return bool(self.token)

    def _call(self, method, path, **kw):
        try:
            resp = requests.request(method, f"{self.base}{path}", timeout=20,
                                    headers={"Authorization": f"Token {self.token}", "Content-Type": "application/json"}, **kw)
        except requests.RequestException as exc:
            raise DeliveryError("Couldn't reach Nepal Can Move. Try again.") from exc
        data = _json(resp)
        if resp.status_code == 401 or resp.status_code == 403:
            raise DeliveryError("Nepal Can Move rejected the API token. Check it in Settings → Shop → Delivery.")
        if resp.status_code >= 400:
            msg = data.get("detail") or data.get("Message") or data.get("message") or data if isinstance(data, dict) else data
            raise DeliveryError(f"Nepal Can Move: {str(msg)[:200]}")
        return data

    def branches(self):
        data = self._call("GET", "/api/v2/branches")
        rows = data if isinstance(data, list) else data.get("results", [])
        return [{"name": b.get("name"), "district": b.get("district_name", ""), "areas": b.get("areas_covered", "")}
                for b in rows if b.get("name")]

    def create(self, order, opts):
        phone = "".join(ch for ch in order.recipient_phone if ch.isdigit())[-10:]
        cod = order.total if order.payment_status != "paid" else Decimal("0")
        payload = {
            "name": order.recipient_name, "phone": phone, "phone2": "",
            "cod_charge": str(int(cod)), "address": f"{order.address}, {order.city}".strip(", "),
            "fbranch": (self.shop.ncm_from_branch or "TINKUNE").upper(),
            "branch": (opts.get("branch") or order.district or order.city or "TINKUNE").upper(),
            "package": ", ".join(f"{i.quantity}x {i.name}" for i in order.items.all())[:200] or "Parcel",
            "vref_id": order.number, "instruction": (opts.get("instruction") or order.note or "")[:200],
            "delivery_type": opts.get("delivery_type") or "Door2Door",
            "weight": str(opts.get("weight") or 1),
        }
        data = self._call("POST", "/api/v1/order/create", json=payload)
        ref = data.get("orderid")
        if not ref:
            raise DeliveryError(f"Nepal Can Move didn't return an order id: {str(data)[:200]}")
        track = str(ref)
        try:
            detail = self._call("GET", "/api/v1/order", params={"id": ref})
            track = detail.get("trackid") or track
        except DeliveryError:
            pass
        return {"courier_ref": str(ref), "tracking_id": str(track), "tracking_url": f"{self.base}/track/{track}",
                "charge": str(data.get("delivery_charge", ""))}

    def status(self, order):
        detail = self._call("GET", "/api/v1/order", params={"id": order.courier_ref})
        return str(detail.get("last_delivery_status") or detail.get("status") or "")


class Pathao:
    key, label = "pathao", "Pathao"

    def __init__(self, shop):
        self.shop = shop
        self.cred = shop.secret("pathao", {}) or {}
        self.base = (shop.pathao_base_url or "https://api-hermes.pathao.com").rstrip("/")

    def enabled(self):
        return bool(self.cred.get("client_id") and self.cred.get("client_secret") and self.cred.get("username"))

    def _token(self):
        if self.cred.get("access_token") and self.cred.get("expires_at", 0) > time.time() + 60:
            return self.cred["access_token"]
        body = {"client_id": self.cred.get("client_id"), "client_secret": self.cred.get("client_secret")}
        if self.cred.get("refresh_token"):
            body.update(grant_type="refresh_token", refresh_token=self.cred["refresh_token"])
        else:
            body.update(grant_type="password", username=self.cred.get("username"), password=self.cred.get("password"))
        try:
            resp = requests.post(f"{self.base}/aladdin/api/v1/issue-token", json=body, timeout=20)
        except requests.RequestException as exc:
            raise DeliveryError("Couldn't reach Pathao.") from exc
        data = _json(resp)
        if resp.status_code >= 400 or not data.get("access_token"):
            if self.cred.get("refresh_token"):  # refresh token expired: fall back to the password grant once
                self.cred.pop("refresh_token", None)
                return self._token()
            raise DeliveryError("Pathao login failed. Check the client ID/secret, email and password in Settings → Shop.")
        self.cred.update(access_token=data["access_token"], refresh_token=data.get("refresh_token", ""),
                         expires_at=int(time.time()) + int(data.get("expires_in", 3600)))
        self.shop.secrets = {**self.shop.secrets, "pathao": self.cred}
        self.shop.save(update_fields=["secrets"])
        return data["access_token"]

    def _call(self, method, path, **kw):
        try:
            resp = requests.request(method, f"{self.base}{path}", timeout=20, headers={
                "Authorization": f"Bearer {self._token()}", "Accept": "application/json"}, **kw)
        except requests.RequestException as exc:
            raise DeliveryError("Couldn't reach Pathao.") from exc
        data = _json(resp)
        if resp.status_code >= 400:
            raise DeliveryError(f"Pathao: {str(data.get('message') or data.get('errors') or data)[:200]}")
        return data.get("data", data)

    def cities(self):
        return [{"id": c["city_id"], "name": c["city_name"]} for c in self._call("GET", "/aladdin/api/v1/city-list").get("data", [])]

    def zones(self, city_id):
        return [{"id": z["zone_id"], "name": z["zone_name"]}
                for z in self._call("GET", f"/aladdin/api/v1/cities/{int(city_id)}/zone-list").get("data", [])]

    def areas(self, zone_id):
        return [{"id": a["area_id"], "name": a["area_name"]}
                for a in self._call("GET", f"/aladdin/api/v1/zones/{int(zone_id)}/area-list").get("data", [])]

    def create(self, order, opts):
        if not (opts.get("city_id") and opts.get("zone_id")):
            raise DeliveryError("Pick the Pathao city and zone for the delivery address.")
        cod = order.total if order.payment_status != "paid" else Decimal("0")
        data = self._call("POST", "/aladdin/api/v1/orders", json={
            "store_id": int(self.shop.pathao_store_id or 0), "merchant_order_id": order.number,
            "recipient_name": order.recipient_name, "recipient_phone": order.recipient_phone,
            "recipient_address": f"{order.address}, {order.city}".strip(", "),
            "recipient_city": int(opts["city_id"]), "recipient_zone": int(opts["zone_id"]),
            **({"recipient_area": int(opts["area_id"])} if opts.get("area_id") else {}),
            "delivery_type": 48, "item_type": 2, "item_quantity": sum(i.quantity for i in order.items.all()) or 1,
            "item_weight": float(opts.get("weight") or 0.5), "amount_to_collect": int(cod),
            "item_description": ", ".join(f"{i.quantity}x {i.name}" for i in order.items.all())[:200],
            "special_instruction": (opts.get("instruction") or order.note or "")[:200],
        })
        cid = data.get("consignment_id")
        if not cid:
            raise DeliveryError(f"Pathao didn't return a consignment id: {str(data)[:200]}")
        return {"courier_ref": str(cid), "tracking_id": str(cid), "tracking_url": "", "charge": str(data.get("delivery_fee", ""))}

    def guess_location(self, order):
        """City / zone ids for automatic booking, matched by name from the order's address. Raises when unsure."""
        def norm(t):
            return " ".join((t or "").lower().replace(",", " ").split())
        place = norm(f"{order.address} {order.city} {order.district}")
        city = next((c for c in self.cities() if norm(c["name"]) and norm(c["name"]) in place), None)
        if not city:
            raise DeliveryError("Couldn't match the address to a Pathao city. Book it from the order page.")
        zones = sorted(self.zones(city["id"]), key=lambda z: -len(z["name"]))
        zone = next((z for z in zones if norm(z["name"]) and norm(z["name"]) in place), None)
        if not zone:
            raise DeliveryError(f"Couldn't match the address to a Pathao zone in {city['name']}. Book it from the order page.")
        return {"city_id": city["id"], "zone_id": zone["id"]}

    def status(self, order):
        try:
            data = self._call("GET", f"/aladdin/api/v1/orders/{order.courier_ref}/info")
        except DeliveryError:
            data = self._call("GET", f"/aladdin/api/v1/orders/{order.courier_ref}")
        return str(data.get("order_status") or data.get("order_status_slug") or "")


def couriers(shop):
    return {c.key: c for c in (NCM(shop), Pathao(shop)) if c.enabled()}


def is_delivered(text):
    t = (text or "").lower()
    return "delivered" in t and "undelivered" not in t and "not delivered" not in t


def is_out_for_delivery(text):
    t = (text or "").lower()
    return any(w in t for w in ("out for delivery", "out_for_delivery", "dispatched to rider", "rider assigned", "on the way"))


def is_returned(text):
    t = (text or "").lower()
    return any(w in t for w in RETURNED_WORDS)
