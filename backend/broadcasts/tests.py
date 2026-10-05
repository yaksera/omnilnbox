import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from automations import comments, engine
from core.models import Workspace
from inbox.models import Conversation, Message
from inbox.services import ingest_message
from integrations.models import ChannelAccount
from integrations.providers import IncomingMessage
from integrations.providers.meta import MetaBaseProvider

from . import services
from .models import Broadcast

PASSWORD = "Kathmandu-Blue-42"


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.content, self.text = data, status, b"1", json.dumps(data)

    def json(self):
        return self._d


class Base(TestCase):
    def setUp(self):
        cache.clear()
        services.DELAY = 0
        self.c = APIClient()
        res = self.c.post("/api/auth/register/", {"name": "Sita Sharma", "email": "sita@example.com", "password": PASSWORD}, format="json")
        self.c.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.ws = Workspace.objects.get()


class BroadcastTests(Base):
    def setUp(self):
        super().setUp()
        self.wa = ChannelAccount.objects.create(workspace=self.ws, provider="whatsapp", name="Shop WA", status="active",
                                                credentials={"access_token": "T", "phone_number_id": "PN1", "business_account_id": "WABA1"})
        for i, name in enumerate(["Anita Gurung", "Bikash Rai", "Chandra Thapa"]):
            ingest_message(self.wa, IncomingMessage(external_thread_id=f"97798000000{i}", contact_external_id=f"97798000000{i}",
                                                    contact_name=name, text="hi", external_message_id=f"m{i}",
                                                    sent_at=timezone.now() - timedelta(days=i * 20)))

    def test_whatsapp_template_broadcast_skips_opted_out(self):
        chandra = Conversation.objects.get(contact__name="Chandra Thapa")
        self.assertIsNotNone(services.handle_opt_out(chandra, "STOP"))
        with mock.patch.object(MetaBaseProvider, "http", staticmethod(lambda m, u, **k: {"data": [
                {"name": "dashain_offer", "language": "en", "status": "APPROVED", "category": "MARKETING",
                 "components": [{"type": "BODY", "text": "Hi {{1}}! Dashain sale: {{2}} off."}]}]})):
            tpl = self.c.get(f"/api/broadcasts/templates/?channel={self.wa.id}").data
        self.assertEqual(tpl[0]["variables"], 2)
        aud = self.c.post("/api/broadcasts/audience/", {"channel_id": str(self.wa.id), "audience": {}}, format="json").data
        self.assertEqual(aud["count"], 2)
        bad = self.c.post("/api/broadcasts/", {"name": "x", "channel_id": str(self.wa.id), "kind": "text", "text": "hi"}, format="json")
        self.assertIn("templates", str(bad.data))
        b = self.c.post("/api/broadcasts/", {"name": "Dashain", "channel_id": str(self.wa.id), "kind": "template",
                                             "template_name": "dashain_offer", "template_language": "en",
                                             "template_body": "Hi {{1}}! Dashain sale: {{2}} off.", "variables": ["{name}", "20%"]},
                        format="json").data
        self.c.post(f"/api/broadcasts/{b['id']}/send/")
        sent = []
        with mock.patch.object(MetaBaseProvider, "http", staticmethod(lambda m, u, **k: sent.append(k["json"]) or {"messages": [{"id": "wamid.1"}]})):
            services.send_batch(b["id"])
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0]["template"]["components"][0]["parameters"][0]["text"], "Anita")
        bc = Broadcast.objects.get()
        self.assertEqual((bc.status, bc.sent, bc.total), ("done", 2, 2))
        self.assertTrue(Message.objects.filter(bot="broadcast", text="Hi Anita! Dashain sale: 20% off.").exists())

    def test_messenger_only_reaches_last_24h(self):
        m = ChannelAccount.objects.create(workspace=self.ws, provider="messenger", name="Page", status="active")
        for i in range(3):
            ingest_message(m, IncomingMessage(external_thread_id=f"P{i}", contact_external_id=f"P{i}", contact_name=f"U{i}",
                                              text="hi", external_message_id=f"x{i}", sent_at=timezone.now() - timedelta(hours=i * 20)))
        self.assertEqual(services.audience(self.ws, m, {"active_days": 30}).count(), 2)  # 0h and 20h ago

    def test_stop_reply_unsubscribes(self):
        msg = ingest_message(self.wa, IncomingMessage(external_thread_id="977980000000", contact_external_id="977980000000",
                                                      text="Stop", external_message_id="stop1"))
        with mock.patch.object(MetaBaseProvider, "http", staticmethod(lambda m, u, **k: {"messages": [{"id": "w"}]})):
            engine.process_incoming(msg.id)
        self.assertTrue(msg.conversation.contact.__class__.objects.get(pk=msg.conversation.contact_id).opted_out)
        self.assertIn("won't receive offers", msg.conversation.messages.filter(direction="out").last().text)

    def test_plan_gate(self):
        Workspace.objects.update(plan="starter", trial_ends_at=None, plan_expires_at=timezone.now() + timedelta(days=30))
        self.assertEqual(self.c.get("/api/broadcasts/").status_code, 402)


@override_settings(PUBLIC_BASE_URL="https://api.shop.test")
class ViberAndWidgetTests(Base):
    def test_viber_webhook_signature_parse_and_reply(self):
        with mock.patch("integrations.providers.base.requests.request", return_value=Resp({"status": 0, "name": "Sita Shop"})):
            res = self.c.post("/api/channels/", {"provider": "viber", "name": "Viber", "credentials": {"auth_token": "VTOKEN"}}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        ch = ChannelAccount.objects.get(provider="viber")
        body = json.dumps({"event": "message", "timestamp": 1790000000000, "message_token": 555,
                           "sender": {"id": "V1", "name": "Ram"}, "message": {"type": "text", "text": "Namaste"}}).encode()
        bad = self.client.post(f"/api/webhooks/{ch.id}/", body, content_type="application/json", HTTP_X_VIBER_CONTENT_SIGNATURE="nope")
        self.assertEqual(bad.status_code, 403)
        sig = hmac.new(b"VTOKEN", body, hashlib.sha256).hexdigest()
        ok = self.client.post(f"/api/webhooks/{ch.id}/", body, content_type="application/json", HTTP_X_VIBER_CONTENT_SIGNATURE=sig)
        self.assertEqual(ok.json()["stored"], 1)
        conv = Conversation.objects.get(channel=ch)
        with mock.patch("integrations.providers.base.requests.request", return_value=Resp({"status": 0, "message_token": 9})) as r:
            self.c.post(f"/api/conversations/{conv.id}/messages/", {"text": "Hajur?"}, format="json")
        sent = r.call_args.kwargs["json"]
        self.assertEqual((sent["receiver"], sent["text"], sent["sender"]["name"]), ("V1", "Hajur?", "Sita Shop"))

    def test_website_widget_chat_roundtrip(self):
        res = self.c.post("/api/channels/", {"provider": "website", "name": "Website", "credentials": {"title": "Chat", "color": "#0f766e"}}, format="json")
        cid = res.data["id"]
        anon = APIClient()
        self.assertEqual(anon.get(f"/api/widget/{cid}/").data["color"], "#0f766e")
        self.assertEqual(anon.get(f"/api/widget/{cid}/messages/").status_code, 401)
        token = anon.post(f"/api/widget/{cid}/session/", {"name": "Hari", "phone": "9800000000"}, format="json").data["token"]
        r = anon.post(f"/api/widget/{cid}/messages/", {"text": "Do you deliver to Butwal?", "name": "Hari", "contact": "9800000000"},
                      format="json", HTTP_X_VISITOR_TOKEN=token)
        self.assertEqual(r.status_code, 201)
        conv = Conversation.objects.get(channel_id=cid)
        self.assertEqual(conv.contact.name, "Hari")
        self.c.post(f"/api/conversations/{conv.id}/messages/", {"text": "Yes! 2-3 days."}, format="json")
        msgs = anon.get(f"/api/widget/{cid}/messages/", HTTP_X_VISITOR_TOKEN=token).data
        self.assertEqual([m["from"] for m in msgs], ["visitor", "agent"])
        other = APIClient().post(f"/api/widget/{cid}/session/", {}, format="json").data["token"]
        self.assertEqual(APIClient().get(f"/api/widget/{cid}/messages/", HTTP_X_VISITOR_TOKEN=other).data, [])  # can't read others


class CommentInboxTests(Base):
    def test_comments_become_conversations_with_public_and_private_replies(self):
        page = ChannelAccount.objects.create(workspace=self.ws, provider="messenger", name="Page", status="active",
                                             credentials={"page_id": "PAGE1", "page_access_token": "PT", "app_secret": "s"})
        body = json.dumps({"object": "page", "entry": [{"id": "PAGE1", "changes": [{"field": "feed", "value": {
            "item": "comment", "verb": "add", "comment_id": "C9", "post_id": "PAGE1_7", "message": "Price kati?",
            "from": {"id": "U5", "name": "Gita Rai"}, "created_time": int(timezone.now().timestamp())}}]}]}).encode()
        comments.handle_webhook(page, body)
        conv = Conversation.objects.get(channel=page)
        data = self.c.get(f"/api/conversations/{conv.id}/").data
        self.assertEqual(data["kind"], "comment")
        calls = []
        with mock.patch.object(MetaBaseProvider, "http", staticmethod(lambda m, u, **k: calls.append((u.split("v21.0/")[1], k["json"])) or {"id": "R1", "message_id": "M1"})):
            self.c.post(f"/api/conversations/{conv.id}/messages/", {"text": "Rs 1,800. Check your DM!"}, format="json")
            r = self.c.post(f"/api/conversations/{conv.id}/private-reply/", {"text": "Namaste Gita, here are the details..."}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(calls[0][0], "C9/comments")
        self.assertEqual(calls[1], ("me/messages", {"recipient": {"comment_id": "C9"}, "message": {"text": "Namaste Gita, here are the details..."}}))
