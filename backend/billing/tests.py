import base64
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.models import Payment
from billing.plans import price_for
from core.models import Workspace


def register(email="owner@example.com", name="Owner One"):
    c = APIClient()
    res = c.post("/api/auth/register/", {"name": name, "email": email, "password": "Kathmandu-Blue-42",
                                         "workspace_name": "Acme"}, format="json")
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    return c


def login(email, password="Kathmandu-Blue-42"):
    c = APIClient()
    tok = c.post("/api/auth/login/", {"email": email, "password": password}, format="json").data["access"]
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
    return c


class PlanTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_prices(self):
        self.assertEqual(price_for("pro", "monthly", "NPR"), Decimal("3999"))
        self.assertEqual(price_for("pro", "yearly", "NPR"), Decimal("38390"))  # 12 x 3999 x 0.8
        self.assertEqual(price_for("pro", "yearly", "USD"), Decimal("278.40"))
        self.assertEqual(price_for("starter", "monthly", "NPR", extra_seats=2), Decimal("2497"))

    def test_public_catalog(self):
        data = APIClient().get("/api/plans/").data
        keys = [p["key"] for p in data["plans"]]
        self.assertEqual(keys, ["free", "starter", "pro", "business", "enterprise"])
        pro = next(p for p in data["plans"] if p["key"] == "pro")
        self.assertEqual(pro["prices"]["NPR"]["monthly"], 3999)
        self.assertTrue(pro["popular"])

    def test_new_workspace_gets_trial_then_falls_back_to_free(self):
        c = register()
        ws = c.get("/api/auth/me/").data["workspace"]
        self.assertEqual(ws["effective_plan"], "pro")
        self.assertTrue(ws["is_trialing"])
        Workspace.objects.update(plan_expires_at=timezone.now() - timedelta(minutes=1))
        ws = c.get("/api/auth/me/").data["workspace"]
        self.assertEqual(ws["effective_plan"], "free")
        self.assertEqual(ws["channel_limit"], 2)


class RoleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = register()

    def _add(self, email, role):
        res = self.owner.post("/api/team/", {"email": email, "role": role}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        token = res.data["url"].rsplit("/", 1)[1]
        info = APIClient().get(f"/api/invites/{token}/").data
        self.assertEqual(info["role"], role)
        acc = APIClient().post(f"/api/invites/{token}/",
                               {"name": "New Person", "password": "Kathmandu-Blue-42"}, format="json")
        self.assertEqual(acc.status_code, 200, acc.data)
        return login(email)

    def test_invite_flow_and_capabilities(self):
        agent = self._add("agent@example.com", "agent")
        me = agent.get("/api/auth/me/").data
        self.assertEqual(me["role"], "agent")
        self.assertNotIn("manage_channels", me["capabilities"])
        # invite token can't be reused
        team = self.owner.get("/api/team/").data
        self.assertEqual(len(team["members"]), 2)
        self.assertEqual(team["invites"], [])
        # agents can't manage channels, team, billing, analytics
        self.assertEqual(agent.post("/api/channels/demo/").status_code, 403)
        self.assertEqual(agent.post("/api/team/", {"email": "z@example.com"}, format="json").status_code, 403)
        self.assertEqual(agent.post("/api/billing/checkout/", {"plan": "pro", "gateway": "esewa"}, format="json").status_code, 403)
        self.assertEqual(agent.get("/api/analytics/").status_code, 403)
        # but they can see billing status (read only) without payment history
        self.assertEqual(agent.get("/api/billing/").data["payments"], [])

    def test_supervisor_and_assignment_rules(self):
        self.owner.post("/api/channels/demo/")
        sup = self._add("sup@example.com", "supervisor")
        agent = self._add("agent2@example.com", "agent")
        agent_id = agent.get("/api/auth/me/").data["user"]["id"]
        sup_id = sup.get("/api/auth/me/").data["user"]["id"]
        conv = self.owner.get("/api/conversations/").data["results"][0]["id"]
        # supervisor can assign to anyone and view analytics
        self.assertEqual(sup.patch(f"/api/conversations/{conv}/", {"assigned_to_id": agent_id}, format="json").status_code, 200)
        self.assertEqual(sup.get("/api/analytics/").status_code, 200)
        # agent can release own conversation but not hand it to someone else
        self.assertEqual(agent.patch(f"/api/conversations/{conv}/", {"assigned_to_id": sup_id}, format="json").status_code, 403)
        self.assertEqual(agent.patch(f"/api/conversations/{conv}/", {"assigned_to_id": None}, format="json").status_code, 200)

    def test_admin_cannot_manage_other_admins_or_owner(self):
        admin = self._add("admin@example.com", "admin")
        other = self._add("admin2@example.com", "admin")
        other_id = other.get("/api/auth/me/").data["user"]["id"]
        owner_id = self.owner.get("/api/auth/me/").data["user"]["id"]
        self.assertEqual(admin.patch(f"/api/team/members/{other_id}/", {"role": "agent"}, format="json").status_code, 403)
        self.assertEqual(admin.delete(f"/api/team/members/{owner_id}/").status_code, 403)
        self.assertEqual(admin.post("/api/team/", {"email": "q@example.com", "role": "admin"}, format="json").status_code, 403)
        # owner can demote and remove
        self.assertEqual(self.owner.patch(f"/api/team/members/{other_id}/", {"role": "agent"}, format="json").status_code, 200)
        self.assertEqual(self.owner.delete(f"/api/team/members/{other_id}/").status_code, 204)

    def test_seat_limit(self):
        Workspace.objects.update(plan="starter", plan_expires_at=timezone.now() + timedelta(days=30), trial_ends_at=None)
        self.assertEqual(self.owner.post("/api/team/", {"email": "a@example.com"}, format="json").status_code, 201)
        res = self.owner.post("/api/team/", {"email": "b@example.com"}, format="json")
        self.assertEqual(res.status_code, 402)  # Starter = 2 seats (owner + 1 pending invite)

    def test_feature_gating(self):
        Workspace.objects.update(plan="free", plan_expires_at=None, trial_ends_at=None)
        self.assertEqual(self.owner.post("/api/tags/", {"name": "vip"}, format="json").status_code, 402)
        self.assertEqual(self.owner.get("/api/analytics/").status_code, 402)
        self.assertEqual(self.owner.post("/api/team/", {"email": "s@example.com", "role": "supervisor"},
                                         format="json").status_code, 403)
        Workspace.objects.update(plan="pro", plan_expires_at=timezone.now() + timedelta(days=30))
        tag = self.owner.post("/api/tags/", {"name": "vip", "color": "#ff0000"}, format="json")
        self.assertEqual(tag.status_code, 201)
        self.owner.post("/api/channels/demo/")
        conv = self.owner.get("/api/conversations/").data["results"][0]["id"]
        self.owner.patch(f"/api/conversations/{conv}/", {"tag_ids": [tag.data["id"]]}, format="json")
        self.assertEqual(self.owner.get(f"/api/conversations/?tag={tag.data['id']}").data["count"], 1)
        note = self.owner.post(f"/api/conversations/{conv}/messages/", {"text": "VIP, handle fast", "note": True}, format="json")
        self.assertTrue(note.data["is_note"])
        self.assertEqual(self.owner.get("/api/analytics/export.csv").status_code, 402)  # Business only
        canned = self.owner.post("/api/canned-replies/", {"shortcut": "hi", "title": "Greeting", "body": "Namaste!"}, format="json")
        self.assertEqual(canned.status_code, 201)


class CheckoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = register()
        self.ws = Workspace.objects.get()

    @override_settings(ESEWA_SECRET_KEY="8gBm/:&EnhH.1/q", ESEWA_PRODUCT_CODE="EPAYTEST")
    def test_esewa_checkout_and_verified_activation(self):
        res = self.owner.post("/api/billing/checkout/", {"plan": "pro", "cycle": "yearly", "gateway": "esewa"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        f = res.data["fields"]
        self.assertEqual(f["total_amount"], "38390")
        payment = Payment.objects.get()

        def cb(status="COMPLETE", total="38390"):
            data = {"transaction_code": "0007ABC", "status": status, "total_amount": total,
                    "transaction_uuid": payment.reference, "product_code": "EPAYTEST",
                    "signed_field_names": "transaction_code,status,total_amount,transaction_uuid,product_code"}
            msg = ",".join(f"{k}={data[k]}" for k in data["signed_field_names"].split(","))
            data["signature"] = base64.b64encode(hmac.new(b"8gBm/:&EnhH.1/q", msg.encode(), hashlib.sha256).digest()).decode()
            return base64.b64encode(json.dumps(data).encode()).decode()

        url = f"/api/billing/return/esewa/{payment.id}/"
        # forged callback (wrong signature) is rejected
        bad = json.loads(base64.b64decode(cb()))
        bad["signature"] = "AAAA"
        r = self.client.get(url, {"data": base64.b64encode(json.dumps(bad).encode()).decode()})
        self.assertIn("payment=failed", r["Location"])
        payment.status = "pending"
        payment.save()
        # valid callback but status API says not complete -> not activated
        with mock.patch("billing.gateways.requests.get") as g:
            g.return_value.json.return_value = {"status": "PENDING"}
            r = self.client.get(url, {"data": cb()})
        self.assertIn("payment=failed", r["Location"])
        payment.status = "pending"
        payment.save()
        with mock.patch("billing.gateways.requests.get") as g:
            g.return_value.json.return_value = {"status": "COMPLETE"}
            r = self.client.get(url, {"data": cb()})
        self.assertIn("payment=success", r["Location"])
        self.ws.refresh_from_db()
        self.assertEqual((self.ws.plan, self.ws.billing_cycle), ("pro", "yearly"))
        self.assertFalse(self.ws.is_trialing)
        self.assertGreater(self.ws.plan_expires_at, timezone.now() + timedelta(days=360))
        # replaying the success callback doesn't extend the plan again
        before = self.ws.plan_expires_at
        with mock.patch("billing.gateways.requests.get") as g:
            g.return_value.json.return_value = {"status": "COMPLETE"}
            self.client.get(url, {"data": cb()})
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.plan_expires_at, before)

    @override_settings(KHALTI_SECRET_KEY="test_key")
    def test_khalti_amount_mismatch_rejected(self):
        with mock.patch("billing.gateways.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"pidx": "PIDX1", "payment_url": "https://test-pay.khalti.com/?pidx=PIDX1"}
            res = self.owner.post("/api/billing/checkout/", {"plan": "starter", "cycle": "monthly", "gateway": "khalti"}, format="json")
        self.assertEqual(res.data["redirect_url"], "https://test-pay.khalti.com/?pidx=PIDX1")
        self.assertEqual(post.call_args.kwargs["json"]["amount"], 149900)  # paisa
        payment = Payment.objects.get()
        with mock.patch("billing.gateways.requests.post") as post:
            post.return_value.json.return_value = {"status": "Completed", "total_amount": 1000}  # tampered amount
            r = self.client.get(f"/api/billing/return/khalti/{payment.id}/", {"pidx": "PIDX1"})
        self.assertIn("payment=failed", r["Location"])
        payment.status = "pending"
        payment.save()
        with mock.patch("billing.gateways.requests.post") as post:
            post.return_value.json.return_value = {"status": "Completed", "total_amount": 149900, "transaction_id": "T1"}
            r = self.client.get(f"/api/billing/return/khalti/{payment.id}/", {"pidx": "PIDX1"})
        self.assertIn("payment=success", r["Location"])
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.effective_plan, "starter")

    @override_settings(STRIPE_SECRET_KEY="sk_test", STRIPE_WEBHOOK_SECRET="whsec_test")
    def test_stripe_webhook_signature(self):
        import time
        with mock.patch("billing.gateways.requests.request") as req:
            req.return_value.status_code = 200
            req.return_value.json.return_value = {"id": "cs_1", "url": "https://checkout.stripe.com/x"}
            self.owner.post("/api/billing/checkout/", {"plan": "business", "gateway": "stripe"}, format="json")
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("69.00"))
        body = json.dumps({"type": "checkout.session.completed", "data": {"object": {
            "client_reference_id": str(payment.id), "payment_status": "paid", "amount_total": 6900}}}).encode()
        self.assertEqual(self.client.post("/api/billing/webhook/stripe/", body, content_type="application/json",
                                          HTTP_STRIPE_SIGNATURE="t=1,v1=bad").status_code, 400)
        ts = int(time.time())
        sig = hmac.new(b"whsec_test", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post("/api/billing/webhook/stripe/", body, content_type="application/json",
                                          HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}").status_code, 200)
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.effective_plan, "business")

    def test_cannot_buy_plan_smaller_than_usage(self):
        self.owner.post("/api/channels/demo/")  # demo channels don't count
        with override_settings(ESEWA_SECRET_KEY="k", ESEWA_PRODUCT_CODE="EPAYTEST"):
            self.assertEqual(self.owner.post("/api/billing/checkout/", {"plan": "enterprise", "gateway": "esewa"},
                                             format="json").status_code, 400)
            self.assertEqual(self.owner.post("/api/billing/checkout/", {"plan": "starter", "gateway": "nope"},
                                             format="json").status_code, 400)

    def test_contact_sales(self):
        res = APIClient().post("/api/contact-sales/", {"name": "Ram", "email": "ram@co.com", "message": "50 seats"}, format="json")
        self.assertEqual(res.status_code, 201)
