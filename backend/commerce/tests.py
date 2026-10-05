import base64
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Workspace
from inbox.models import Message
from inbox.services import ingest_message
from integrations.models import ChannelAccount
from integrations.providers import IncomingMessage

from . import services
from .models import Customer, Order, PaymentLink, Product, ShopSettings

PASSWORD = "Kathmandu-Blue-42"


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self._data


@override_settings(PUBLIC_BASE_URL="https://api.shop.test", FRONTEND_URL="https://app.shop.test")
class CommerceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()
        res = self.c.post("/api/auth/register/", {"name": "Sita Sharma", "email": "sita@example.com", "password": PASSWORD}, format="json")
        self.c.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.ws = Workspace.objects.get()
        self.channel = ChannelAccount.objects.create(workspace=self.ws, provider="whatsapp", name="Shop WA", status="active", is_demo=True)
        msg = ingest_message(self.channel, IncomingMessage(external_thread_id="9779812345678", contact_external_id="9779812345678",
                                                           contact_name="Anita Gurung", contact_handle="+9779812345678",
                                                           text="2 kurta order garna milcha?", external_message_id="m1"))
        self.conv = msg.conversation
        self.kurta = self.c.post("/api/products/", {"name": "Cotton kurta", "price": "1800", "stock": 10,
                                                   "variants": ["S", "M", "L"]}, format="json").data

    def new_order(self, **extra):
        body = {"conversation_id": str(self.conv.id), "items": [{"product_id": self.kurta["id"], "variant": "M", "quantity": 2}],
                "recipient_name": "Anita Gurung", "recipient_phone": "9812345678", "address": "Lakeside-6", "city": "Pokhara",
                "district": "Kaski", "payment_method": "khalti", **extra}
        res = self.c.post("/api/orders/", body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def outgoing(self):
        return list(self.conv.messages.filter(direction="out", is_note=False).values_list("text", flat=True))

    def test_order_from_chat_links_customer_totals_and_stock(self):
        o = self.new_order()
        self.assertEqual(o["number"], "#1001")
        self.assertEqual(o["subtotal"], "3600.00")
        self.assertEqual(o["delivery_charge"], "150.00")  # outside the valley
        self.assertEqual(o["total"], "3750.00")
        self.assertEqual(Product.objects.get().stock, 8)
        cust = Customer.objects.get()
        self.assertEqual(cust.phone, "9812345678")
        self.assertEqual(self.conv.contact.__class__.objects.get(pk=self.conv.contact_id).customer_id, cust.id)
        panel = self.c.get(f"/api/conversations/{self.conv.id}/customer/").data
        self.assertEqual(panel["customer"]["orders_count"], 1)
        self.assertEqual(panel["customer"]["total_spent"], "3750.00")
        # editing items gives stock back first
        self.c.put(f"/api/orders/{o['id']}/", {"items": [{"product_id": self.kurta["id"], "quantity": 1}]}, format="json")
        self.assertEqual(Product.objects.get().stock, 9)
        self.assertEqual(self.new_order()["number"], "#1002")

    @override_settings(DEBUG=True)
    def test_khalti_payment_link_end_to_end(self):
        shop = ShopSettings.for_workspace(self.ws)
        self.assertEqual(self.c.put("/api/shop/settings/", {"khalti_secret_key": "live_secret_key_abc"}, format="json").status_code, 200)
        self.assertNotIn("live_secret_key_abc", json.dumps(self.c.get("/api/shop/settings/").data))  # never sent back
        o = self.new_order()
        res = self.c.post(f"/api/orders/{o['id']}/send-summary/", format="json")
        self.assertEqual(res.status_code, 200, res.data)
        summary = self.outgoing()[-1]
        self.assertIn("Order #1001", summary.replace("order #", "Order #"))
        self.assertIn("3,750", summary)
        link = PaymentLink.objects.get()
        self.assertIn(f"https://app.shop.test/pay/{link.id}", summary)
        public = APIClient().get(f"/api/pay/{link.id}/").data
        self.assertEqual(public["amount"], "3750.00")
        self.assertIn("khalti", public["gateways"])
        calls = []

        def post(url, json=None, **kw):
            calls.append((url, json, kw["headers"]["Authorization"]))
            if url.endswith("/initiate/"):
                return Resp({"pidx": "PIDX1", "payment_url": "https://pay.khalti.com/?pidx=PIDX1"})
            return Resp({"status": "Completed", "total_amount": 375000, "transaction_id": "TXN9"})
        with mock.patch("commerce.payments.requests.post", side_effect=post):
            start = APIClient().post(f"/api/pay/{link.id}/start/khalti/").data
            self.assertEqual(start["redirect_url"], "https://pay.khalti.com/?pidx=PIDX1")
            self.assertEqual(calls[0][1]["amount"], 375000)
            self.assertEqual(calls[0][2], "Key live_secret_key_abc")  # the SHOP's key, not OmniInbox's
            self.assertTrue(calls[0][1]["return_url"].startswith(f"https://api.shop.test/api/pay/{link.id}/return/khalti/"))
            back = self.client.get(f"/api/pay/{link.id}/return/khalti/", {"pidx": "PIDX1", "status": "Completed"})
        self.assertEqual(back["Location"], f"https://app.shop.test/pay/{link.id}?result=success")
        order = Order.objects.get(id=o["id"])
        self.assertEqual((order.payment_status, order.status), ("paid", "confirmed"))
        self.assertIn("Payment received", self.outgoing()[-1])
        self.assertTrue(self.conv.messages.filter(is_note=True, text__contains="paid").exists())
        shop.refresh_from_db()

    @override_settings(DEBUG=True)
    def test_forged_esewa_callback_is_rejected(self):
        o = self.new_order(payment_method="esewa")
        link = services.create_payment_link(Order.objects.get(id=o["id"]))
        start = APIClient().post(f"/api/pay/{link.id}/start/esewa/").data
        self.assertEqual(start["fields"]["product_code"], "EPAYTEST")  # sandbox in development
        forged = base64.b64encode(json.dumps({"status": "COMPLETE", "total_amount": "3750", "transaction_uuid": str(link.id),
                                              "signed_field_names": "status", "signature": "nope"}).encode()).decode()
        r = self.client.get(f"/api/pay/{link.id}/return/esewa/", {"data": forged})
        self.assertIn("result=failed", r["Location"])
        self.assertEqual(Order.objects.get(id=o["id"]).payment_status, "pending")

    def test_ncm_booking_and_tracking_marks_cod_paid_on_delivery(self):
        self.c.put("/api/shop/settings/", {"ncm_token": "tok123"}, format="json")
        o = self.new_order(payment_method="cod")
        sent = []

        def request(method, url, **kw):
            sent.append((method, url, kw.get("json"), kw["headers"]["Authorization"]))
            if url.endswith("/order/create"):
                return Resp({"orderid": 5551, "delivery_charge": 150})
            if "/api/v1/order" in url:
                return Resp({"trackid": "NCM5551", "last_delivery_status": "Delivered"})
            return Resp({})
        with mock.patch("commerce.delivery.requests.request", side_effect=request):
            res = self.c.post(f"/api/orders/{o['id']}/ship/", {"courier": "ncm", "branch": "POKHARA"}, format="json")
            self.assertEqual(res.status_code, 200, res.data)
            self.assertEqual(res.data["tracking_id"], "NCM5551")
            self.assertEqual(res.data["status"], "shipped")
            payload = sent[0][2]
            self.assertEqual((payload["cod_charge"], payload["branch"], payload["phone"]), ("3750", "POKHARA", "9812345678"))
            self.assertEqual(sent[0][3], "Token tok123")
            self.assertIn("on the way", self.outgoing()[-1])
            Order.objects.update(delivery_checked_at=timezone.now() - timedelta(hours=1))
            self.assertEqual(services.sync_deliveries(), 1)
        order = Order.objects.get(id=o["id"])
        self.assertEqual((order.status, order.payment_status), ("delivered", "paid"))

    def test_manual_shipping_and_merge_customers(self):
        o = self.new_order(payment_method="cod")
        r = self.c.post(f"/api/orders/{o['id']}/ship/", {"courier": "manual", "courier_name": "Upaya",
                                                         "tracking_id": "UP-77", "tracking_url": "javascript:alert(1)"}, format="json")
        self.assertEqual(r.data["tracking_url"], "")  # only http(s) links are kept
        self.assertEqual(r.data["courier_name"], "Upaya")
        other = Customer.objects.create(workspace=self.ws, name="Anita G", email="anita@example.com")
        keep = Customer.objects.exclude(pk=other.pk).get()
        merged = self.c.post(f"/api/customers/{keep.id}/merge/", {"other_id": str(other.id)}, format="json").data
        self.assertEqual(merged["email"], "anita@example.com")
        self.assertEqual(Customer.objects.count(), 1)

    def test_plans_and_roles(self):
        inv = self.c.post("/api/team/", {"email": "agent@example.com", "role": "agent"}, format="json").data
        APIClient().post(f"/api/invites/{inv['url'].rsplit('/', 1)[1]}/", {"name": "Agent A", "password": PASSWORD}, format="json")
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION="Bearer " + agent.post(
            "/api/auth/login/", {"email": "agent@example.com", "password": PASSWORD}, format="json").data["access"])
        self.assertEqual(agent.put("/api/shop/settings/", {"khalti_secret_key": "x"}, format="json").status_code, 403)
        self.assertEqual(agent.post("/api/products/", {"name": "x", "price": "1"}, format="json").status_code, 403)
        self.assertEqual(agent.post("/api/orders/", {"items": [{"name": "Custom", "unit_price": "500"}]}, format="json").status_code, 201)
        # Starter: orders yes, courier booking no
        Workspace.objects.update(plan="starter", trial_ends_at=None, plan_expires_at=timezone.now() + timedelta(days=30))
        o = self.new_order(payment_method="cod")
        self.assertEqual(self.c.post(f"/api/orders/{o['id']}/ship/", {"courier": "ncm"}, format="json").status_code, 402)
        self.assertEqual(self.c.post(f"/api/orders/{o['id']}/ship/", {"courier": "self"}, format="json").status_code, 200)
        Workspace.objects.update(plan="free", plan_expires_at=None)
        self.assertEqual(self.c.get("/api/orders/").status_code, 402)

    def test_payment_link_rejects_changed_total(self):
        self.c.put("/api/shop/settings/", {"khalti_secret_key": "k"}, format="json")
        o = self.new_order()
        link = services.create_payment_link(Order.objects.get(id=o["id"]))
        Order.objects.filter(id=o["id"]).update(total=Decimal("10"))
        self.assertEqual(APIClient().post(f"/api/pay/{link.id}/start/khalti/").status_code, 400)
        self.assertEqual(Message.objects.filter(conversation=self.conv, direction="out").count(), 0)
