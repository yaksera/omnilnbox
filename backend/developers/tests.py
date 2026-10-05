import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from automations import engine
from core.models import Workspace
from inbox.models import Conversation, CsatResponse
from inbox.services import ingest_message, parse_rating
from integrations.models import ChannelAccount
from integrations.providers import IncomingMessage

from . import events
from .models import WebhookDelivery, WebhookEndpoint

PASSWORD = "Kathmandu-Blue-42"


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()
        res = self.c.post("/api/auth/register/", {"name": "Sita Sharma", "email": "sita@example.com", "password": PASSWORD}, format="json")
        self.c.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.ws = Workspace.objects.get()

    def business(self):
        Workspace.objects.update(plan="business", trial_ends_at=None, plan_expires_at=timezone.now() + timedelta(days=30))


class ApiKeyTests(Base):
    def test_api_key_auth_scope_and_revoke(self):
        self.assertEqual(self.c.post("/api/developers/api-keys/", {"name": "Zapier"}, format="json").status_code, 402)  # Pro trial
        self.business()
        created = self.c.post("/api/developers/api-keys/", {"name": "Zapier"}, format="json").data
        raw = created["key"]
        self.assertTrue(raw.startswith("omni_"))
        self.assertNotIn("key", self.c.get("/api/developers/api-keys/").data[0])  # never shown again
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
        self.assertEqual(api.get("/api/conversations/").status_code, 200)
        self.assertEqual(APIClient().get("/api/conversations/", HTTP_X_API_KEY=raw).status_code, 200)
        other = Workspace.objects.create(name="Other", slug="other")
        self.assertEqual(api.get("/api/conversations/", HTTP_X_WORKSPACE_ID=str(other.id)).status_code, 200)  # still pinned to its own
        self.c.delete(f"/api/developers/api-keys/{created['id']}/")
        self.assertEqual(api.get("/api/conversations/").status_code, 401)
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Bearer omni_nope")
        self.assertEqual(bad.get("/api/conversations/").status_code, 401)


class WebhookTests(Base):
    def test_signed_delivery_and_ssrf_guard(self):
        self.business()
        self.assertEqual(self.c.post("/api/developers/webhooks/", {"url": "http://x.test/h", "events": ["order.paid"]}, format="json").status_code, 400)
        h = self.c.post("/api/developers/webhooks/", {"url": "https://hooks.example.com/omni", "events": ["message.received"]}, format="json").data
        ep = WebhookEndpoint.objects.get()
        posted = []
        with mock.patch("core.netguard.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), \
                mock.patch("developers.events.requests.post", side_effect=lambda url, **kw: posted.append(kw) or mock.Mock(status_code=200, text="ok")):
            ch = ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="Bot", status="active")
            run_inline = lambda fn, ep_id, event, payload: events.deliver_now(WebhookEndpoint.objects.get(id=ep_id), event, payload)  # noqa: E731
            with mock.patch.object(events._pool, "submit", side_effect=run_inline), \
                    mock.patch("automations.engine._pool.submit"), self.captureOnCommitCallbacks(execute=True):
                ingest_message(ch, IncomingMessage(external_thread_id="1", contact_external_id="1", contact_name="Ram", text="hello", external_message_id="m1"))
        self.assertEqual(len(posted), 1)
        body = posted[0]["data"]
        self.assertEqual(posted[0]["headers"]["X-Omni-Signature"], "sha256=" + hmac.new(h["secret"].encode(), body, hashlib.sha256).hexdigest())
        self.assertEqual(json.loads(body)["data"]["text"], "hello")
        # private addresses are refused
        ep.url = "https://127.0.0.1/steal"
        ep.save()
        d = events.deliver_now(ep, "ping", {"id": "t"}, retries=(0,))
        self.assertIn("private address", d.error)
        self.assertEqual(WebhookDelivery.objects.count(), 2)


class CsatTests(Base):
    def test_survey_after_close_and_rating(self):
        self.c.patch("/api/workspace/", {"csat_enabled": True}, format="json")
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="Bot", status="active", is_demo=True)
        msg = ingest_message(ch, IncomingMessage(external_thread_id="1", contact_external_id="1", contact_name="Ram", text="hi", external_message_id="m1"))
        conv = msg.conversation
        self.c.post(f"/api/conversations/{conv.id}/messages/", {"text": "Namaste! Your order ships today."}, format="json")
        self.c.patch(f"/api/conversations/{conv.id}/", {"status": "closed"}, format="json")
        conv.refresh_from_db()
        self.assertIn("csat_pending", conv.meta)
        self.assertIn("1 (bad) to 5", conv.messages.filter(direction="out").order_by("sent_at").last().text)
        reply = ingest_message(ch, IncomingMessage(external_thread_id="1", contact_external_id="1", text="5 very fast, thanks!", external_message_id="m9"))
        engine.process_incoming(reply.id)
        r = CsatResponse.objects.get()
        self.assertEqual((r.score, r.comment), (5, "very fast, thanks!"))
        conv.refresh_from_db()
        self.assertEqual(conv.status, "closed")
        data = self.c.get("/api/analytics/?days=7").data
        self.assertEqual(data["csat"]["avg"], 5)
        self.assertEqual(data["sla"]["target_minutes"], 60)

    def test_parse_rating(self):
        self.assertEqual(parse_rating("4"), (4, ""))
        self.assertEqual(parse_rating("⭐⭐⭐"), (3, ""))
        self.assertEqual(parse_rating("2 - slow reply"), (2, "slow reply"))
        self.assertIsNone(parse_rating("I want 3 kurtas"))
        self.assertIsNone(parse_rating("9"))


class BrandTests(Base):
    def test_white_label_business_only(self):
        self.assertEqual(self.c.put("/api/workspace/brand/", {"brand_name": "Kathmandu Digital"}, format="json").status_code, 402)
        self.business()
        self.assertEqual(self.c.put("/api/workspace/brand/", {"brand_color": "red"}, format="json").status_code, 400)
        r = self.c.put("/api/workspace/brand/", {"brand_name": "Kathmandu Digital", "brand_color": "#0f766e", "hide_powered_by": True}, format="json")
        self.assertEqual(r.data["name"], "Kathmandu Digital")
        self.assertTrue(self.c.get("/api/auth/me/").data["workspace"]["brand"]["hide_powered_by"])
