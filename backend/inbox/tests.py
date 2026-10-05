import hashlib
import hmac
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from integrations.models import ChannelAccount


class BaseAPITest(TestCase):
    def setUp(self):
        cache.clear()  # reset rate-limit counters between tests
        self.client = APIClient()
        res = self.client.post("/api/auth/register/", {
            "name": "Griha Test", "email": "owner@example.com", "password": "Kathmandu-Blue-42",
            "workspace_name": "Acme",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.workspace_id = self.client.get("/api/auth/me/").data["workspace"]["id"]


class AuthTests(BaseAPITest):
    def test_login_and_me(self):
        c = APIClient()
        res = c.post("/api/auth/login/", {"email": "owner@example.com", "password": "Kathmandu-Blue-42"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)
        res = c.post("/api/auth/login/", {"email": "owner@example.com", "password": "wrong"}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_tenant_isolation(self):
        self.client.post("/api/channels/demo/")
        other = APIClient()
        res = other.post("/api/auth/register/", {"name": "Eve", "email": "eve@example.com", "password": "Kathmandu-Blue-42"}, format="json")
        other.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.assertEqual(other.get("/api/conversations/").data["count"], 0)
        self.assertEqual(other.get("/api/channels/").data, [])


class DemoInboxTests(BaseAPITest):
    def test_demo_flow(self):
        res = self.client.post("/api/channels/demo/")
        self.assertEqual(res.data["created"], 9)
        convs = self.client.get("/api/conversations/").data
        self.assertEqual(convs["count"], 11)
        stats = self.client.get("/api/stats/").data
        self.assertEqual(stats["unread_messages"], 11)
        self.assertIn("whatsapp", stats["by_provider"])

        wa = self.client.get("/api/conversations/?provider=whatsapp").data["results"]
        self.assertEqual(len(wa), 2)
        conv_id = wa[0]["id"]
        res = self.client.post(f"/api/conversations/{conv_id}/messages/", {"text": "Yes, size M is in stock!"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["status"], "sent")
        msgs = self.client.get(f"/api/conversations/{conv_id}/messages/").data
        self.assertEqual([m["direction"] for m in msgs], ["in", "out", "in"])  # demo auto-reply

        res = self.client.patch(f"/api/conversations/{conv_id}/", {"status": "closed"}, format="json")
        self.assertEqual(res.data["status"], "closed")
        self.assertEqual(self.client.get("/api/conversations/?q=hoodie").data["count"], 1)
        self.assertEqual(self.client.get("/api/conversations/?category=email").data["count"], 3)


class ChannelTests(BaseAPITest):
    def test_providers_listed(self):
        keys = {p["key"] for p in self.client.get("/api/providers/").data}
        self.assertTrue({"whatsapp", "instagram", "messenger", "tiktok", "telegram", "discord",
                         "gmail", "outlook", "zoho"} <= keys)

    def test_credentials_are_masked_and_encrypted(self):
        with mock.patch("integrations.providers.telegram.TelegramProvider._call", return_value={"username": "bot", "id": 1}):
            res = self.client.post("/api/channels/", {
                "provider": "telegram", "name": "Support bot",
                "credentials": {"bot_token": "123:SECRET", "mode": "polling"},
            }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["credentials_preview"]["bot_token"], "••••••••")
        ch = ChannelAccount.objects.get(id=res.data["id"])
        self.assertEqual(ch.status, "active")
        self.assertEqual(ch.credentials["bot_token"], "123:SECRET")
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT credentials FROM integrations_channelaccount")
            raw = cur.fetchone()[0]
        self.assertNotIn("SECRET", raw)

    def test_plan_limit(self):
        from core.models import Workspace
        Workspace.objects.filter(id=self.workspace_id).update(plan="free", plan_expires_at=None, trial_ends_at=None)
        with mock.patch("integrations.providers.telegram.TelegramProvider._call", return_value={}):
            for i in range(2):
                self.client.post("/api/channels/", {"provider": "telegram", "name": f"b{i}",
                                                    "credentials": {"bot_token": "x"}}, format="json")
            res = self.client.post("/api/channels/", {"provider": "telegram", "name": "b3",
                                                      "credentials": {"bot_token": "x"}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Free plan allows 2", str(res.data))


class WebhookTests(BaseAPITest):
    def _channel(self, provider, creds):
        from core.models import Workspace
        return ChannelAccount.objects.create(
            workspace=Workspace.objects.get(id=self.workspace_id), provider=provider,
            name=provider, credentials=creds, status="active",
        )

    def test_telegram_webhook(self):
        ch = self._channel("telegram", {"bot_token": "x", "mode": "webhook"})
        update = {"update_id": 1, "message": {"message_id": 7, "date": 1700000000, "text": "hello",
                                                "chat": {"id": 555}, "from": {"id": 555, "first_name": "Ram", "username": "ram"}}}
        url = f"/api/webhooks/{ch.id}/"
        bad = self.client.post(url, update, format="json")
        self.assertEqual(bad.status_code, 403)
        ok = self.client.post(url, update, format="json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=ch.webhook_secret)
        self.assertEqual(ok.json()["stored"], 1)
        dup = self.client.post(url, update, format="json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=ch.webhook_secret)
        self.assertEqual(dup.json()["stored"], 0)
        conv = self.client.get("/api/conversations/").data["results"][0]
        self.assertEqual(conv["contact"]["handle"], "@ram")

        with mock.patch("integrations.providers.telegram.TelegramProvider._call", return_value={"message_id": 8}) as call:
            res = self.client.post(f"/api/conversations/{conv['id']}/messages/", {"text": "hi Ram"}, format="json")
        self.assertEqual(res.status_code, 201)
        call.assert_called_with("sendMessage", chat_id="555", text="hi Ram")

    def test_whatsapp_webhook_signature_and_challenge(self):
        ch = self._channel("whatsapp", {"access_token": "t", "phone_number_id": "PN1", "app_secret": "shh", "verify_token": "vt"})
        url = f"/api/webhooks/{ch.id}/"
        res = self.client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"})
        self.assertEqual(res.content, b"42")
        body = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "PN1"},
            "contacts": [{"wa_id": "9779800000000", "profile": {"name": "Hari"}}],
            "messages": [{"from": "9779800000000", "id": "wamid.1", "timestamp": "1700000000",
                          "type": "text", "text": {"body": "Namaste"}}],
        }}]}]}).encode()
        sig = "sha256=" + hmac.new(b"shh", body, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post(url, body, content_type="application/json").status_code, 403)
        res = self.client.post(url, body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual(res.json()["stored"], 1)
        conv = self.client.get("/api/conversations/").data["results"][0]
        self.assertEqual(conv["contact"]["name"], "Hari")
        self.assertEqual(conv["last_message_preview"], "Namaste")

    def test_instagram_echo_is_outgoing(self):
        ch = self._channel("instagram", {"ig_account_id": "IG1", "page_access_token": "t", "app_secret": "s"})
        body = json.dumps({"object": "instagram", "entry": [{"messaging": [
            {"sender": {"id": "U1"}, "recipient": {"id": "IG1"}, "timestamp": 1700000000000, "message": {"mid": "m1", "text": "hey"}},
            {"sender": {"id": "IG1"}, "recipient": {"id": "U1"}, "timestamp": 1700000001000, "message": {"mid": "m2", "text": "hello!", "is_echo": True}},
        ]}]}).encode()
        sig = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
        with mock.patch("integrations.providers.meta.InstagramProvider._profile", return_value={"name": "Sam", "username": "sam"}):
            res = self.client.post(f"/api/webhooks/{ch.id}/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual(res.json()["stored"], 2)
        conv = self.client.get("/api/conversations/").data["results"][0]
        msgs = self.client.get(f"/api/conversations/{conv['id']}/messages/").data
        self.assertEqual([m["direction"] for m in msgs], ["in", "out"])
        self.assertEqual(conv["unread_count"], 1)


class EmailParsingTests(TestCase):
    def test_extract_body_and_thread_root(self):
        import email
        import email.policy

        from integrations.providers.email_imap import extract_body, thread_root
        raw = (b"From: A <a@x.com>\r\nTo: b@y.com\r\nSubject: Re: Hi\r\nMessage-ID: <3@x>\r\n"
               b"References: <1@y> <2@x>\r\nIn-Reply-To: <2@x>\r\nContent-Type: text/plain\r\n\r\n"
               b"Sounds good!\r\n\r\nOn Mon, B wrote:\r\n> earlier text\r\n")
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        text, html, atts = extract_body(msg)
        self.assertEqual(text, "Sounds good!")
        self.assertEqual(thread_root(msg), "<1@y>")


class MessengerConnectTests(TestCase):  # noqa: D101
    def test_user_token_is_exchanged_for_page_token_and_page_subscribed(self):
        from core.models import Workspace
        from integrations.views import _connect
        ws = Workspace.objects.create(name="W")
        ch = ChannelAccount.objects.create(workspace=ws, provider="messenger", name="m", credentials={
            "page_id": "PAGE1", "page_access_token": "USERTOKEN", "app_secret": "s"})
        calls = []

        def fake_graph(self, method, path, token, **kw):
            calls.append((method, path, token))
            if path == "me/accounts":
                return {"data": [{"id": "PAGE1", "name": "My Shop", "access_token": "PAGETOKEN"}]}
            if path == "PAGE1/subscribed_apps":
                return {"success": True}
            raise AssertionError(path)

        with mock.patch("integrations.providers.meta.MetaBaseProvider.graph", fake_graph):
            info = _connect(ch)
        ch.refresh_from_db()
        self.assertEqual(ch.status, "active", ch.last_error)
        self.assertEqual(ch.credentials["page_access_token"], "PAGETOKEN")
        self.assertEqual(info["page"], "My Shop")
        self.assertIn(("POST", "PAGE1/subscribed_apps", "PAGETOKEN"), calls)


    def test_wrong_page_id_lists_available_pages(self):
        from core.models import Workspace
        from integrations.views import _connect
        ws = Workspace.objects.create(name="W2")
        ch = ChannelAccount.objects.create(workspace=ws, provider="messenger", name="m", credentials={
            "page_id": "APPID", "page_access_token": "USERTOKEN", "app_secret": "s"})

        def fake_graph(self, method, path, token, **kw):
            return {"data": [{"id": "PAGE1", "name": "My Shop", "access_token": "PT"}]}

        with mock.patch("integrations.providers.meta.MetaBaseProvider.graph", fake_graph):
            _connect(ch)
        ch.refresh_from_db()
        self.assertEqual(ch.status, "error")
        self.assertIn("My Shop (PAGE1)", ch.last_error)


class MessengerPollingTests(TestCase):
    def test_poll_imports_customer_and_page_messages(self):
        from core.models import Workspace
        from integrations.sync import sync_channel
        ws = Workspace.objects.create(name="W3")
        ch = ChannelAccount.objects.create(workspace=ws, provider="messenger", name="m", status="active", credentials={
            "page_id": "PAGE1", "page_access_token": "PT", "app_secret": "s"})
        payload = {"data": [{
            "updated_time": "2026-09-30T11:26:23+0000",
            "participants": {"data": [{"name": "Anish", "id": "U1"}, {"name": "Shop", "id": "PAGE1"}]},
            "messages": {"data": [
                {"id": "m_3", "message": "What is the price", "from": {"id": "U1"}, "created_time": "2026-09-30T11:26:23+0000"},
                {"id": "m_2", "message": "Hello", "from": {"id": "PAGE1"}, "created_time": "2026-09-30T11:26:05+0000"},
                {"id": "m_1", "message": "Heloo", "from": {"id": "U1"}, "created_time": "2026-09-30T11:04:42+0000"},
            ]},
        }]}
        with mock.patch("integrations.providers.meta.MetaBaseProvider.graph", return_value=payload):
            self.assertEqual(sync_channel(ch), 3)
            self.assertEqual(sync_channel(ch), 0)  # nothing new
        from inbox.models import Conversation
        conv = Conversation.objects.get(channel=ch)
        self.assertEqual(conv.contact.name, "Anish")
        self.assertEqual(conv.external_thread_id, "U1")
        self.assertEqual([m.direction for m in conv.messages.all()], ["in", "out", "in"])
        self.assertEqual(conv.last_message_preview, "What is the price")



class SecurityTests(BaseAPITest):
    def test_weak_password_rejected(self):
        res = APIClient().post("/api/auth/register/", {"name": "W", "email": "w@example.com", "password": "password123"},
                               format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.data)

    def test_login_is_rate_limited(self):
        cache.clear()
        c = APIClient()
        codes = [c.post("/api/auth/login/", {"email": "owner@example.com", "password": "nope"}, format="json").status_code
                 for _ in range(22)]
        self.assertIn(429, codes)

    def test_logout_revokes_refresh_token(self):
        cache.clear()
        c = APIClient()
        tokens = c.post("/api/auth/login/", {"email": "owner@example.com", "password": "Kathmandu-Blue-42"}, format="json").data
        self.assertEqual(c.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code, 205)
        self.assertEqual(c.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code, 401)

    def test_used_refresh_token_cannot_be_reused(self):
        cache.clear()
        c = APIClient()
        tokens = c.post("/api/auth/login/", {"email": "owner@example.com", "password": "Kathmandu-Blue-42"}, format="json").data
        self.assertEqual(c.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code, 401)

    def test_bad_workspace_header(self):
        res = self.client.get("/api/conversations/", HTTP_X_WORKSPACE_ID="not-a-uuid")
        self.assertEqual(res.status_code, 403)
        res = self.client.get("/api/conversations/", HTTP_X_WORKSPACE_ID="00000000-0000-0000-0000-000000000000")
        self.assertEqual(res.status_code, 403)

    def test_unknown_credential_fields_rejected(self):
        res = self.client.post("/api/channels/", {"provider": "outlook", "name": "o", "credentials": {
            "client_id": "a", "client_secret": "b", "refresh_token": "injected"}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("refresh_token", str(res.data))

    def test_invite_role_rules(self):
        self.assertEqual(self.client.post("/api/team/", {"email": "x@example.com", "role": "owner"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/team/", {"email": "not-an-email"}, format="json").status_code, 400)

    @override_settings(ALLOW_PRIVATE_HOSTS=False)
    def test_imap_ssrf_to_internal_host_blocked(self):
        res = self.client.post("/api/channels/", {"provider": "imap", "name": "evil", "credentials": {
            "email": "a@b.com", "password": "x", "imap_host": "127.0.0.1", "imap_port": "993",
            "smtp_host": "169.254.169.254", "smtp_port": "465"}}, format="json")
        self.assertEqual(res.status_code, 201)
        ch = ChannelAccount.objects.get(id=res.data["id"])
        self.assertEqual(ch.status, "error")
        self.assertIn("private address", ch.last_error)

    def test_tiktok_webhook_requires_valid_recent_signature(self):
        import time as _t
        from core.models import Workspace
        ch = ChannelAccount.objects.create(workspace=Workspace.objects.get(id=self.workspace_id), provider="tiktok",
                                           name="t", status="active",
                                           credentials={"access_token": "a", "business_id": "B", "app_secret": "sek"})
        body = b'{"content": {"message": {"text": "hi"}, "sender": {"id": "U"}, "conversation_id": "C"}}'
        url = f"/api/webhooks/{ch.id}/"
        self.assertEqual(self.client.post(url, body, content_type="application/json").status_code, 403)
        old = str(int(_t.time()) - 3600)
        sig = hmac.new(b"sek", f"{old}.".encode() + body, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post(url, body, content_type="application/json",
                                          HTTP_TIKTOK_SIGNATURE=f"t={old},s={sig}").status_code, 403)
        now = str(int(_t.time()))
        sig = hmac.new(b"sek", f"{now}.".encode() + body, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post(url, body, content_type="application/json",
                                          HTTP_TIKTOK_SIGNATURE=f"t={now},s={sig}").status_code, 200)

    def test_security_headers(self):
        res = self.client.get("/health/")
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")
        self.assertEqual(res["X-Frame-Options"], "DENY")


class PerformanceTests(BaseAPITest):
    def test_incremental_messages_and_single_query_stats(self):
        self.client.post("/api/channels/demo/")
        conv = self.client.get("/api/conversations/?provider=telegram").data["results"][0]
        msgs = self.client.get(f"/api/conversations/{conv['id']}/messages/").data
        last = msgs[-1]["created_at"]
        self.assertEqual(self.client.get(f"/api/conversations/{conv['id']}/messages/", {"after": last}).data, [])
        self.client.post(f"/api/conversations/{conv['id']}/messages/", {"text": "hi"}, format="json")
        fresh = self.client.get(f"/api/conversations/{conv['id']}/messages/", {"after": last}).data
        self.assertEqual([m["direction"] for m in fresh], ["out", "in"])
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            stats = self.client.get("/api/stats/").data
        self.assertEqual(stats["unread_messages"], 11)  # 10 untouched + demo auto-reply
        self.assertLessEqual(len(ctx.captured_queries), 6)



class HandoverTests(TestCase):
    def _channel(self):
        from core.models import Workspace
        from inbox.models import Contact, Conversation
        ws = Workspace.objects.create(name="H")
        ch = ChannelAccount.objects.create(workspace=ws, provider="messenger", name="m", status="active",
                                           credentials={"page_id": "P", "page_access_token": "PT", "app_secret": "s"})
        ct = Contact.objects.create(workspace=ws, channel=ch, external_id="U1", name="Anish")
        return Conversation.objects.create(workspace=ws, channel=ch, contact=ct, external_thread_id="U1")

    def _err(self, sub):
        from integrations.providers.base import ProviderError
        return ProviderError("400", status=400, detail={"error": {"code": 10, "error_subcode": sub}})

    def test_takes_thread_control_and_retries(self):
        from inbox.services import send_reply
        conv = self._channel()
        calls = []

        def fake(self_, method, path, token, **kw):
            calls.append(path)
            if path == "me/messages" and calls.count("me/messages") == 1:
                raise HandoverTests._err(None, 2018300)
            return {"message_id": "m_ok"} if path == "me/messages" else {"success": True}

        with mock.patch("integrations.providers.meta.MetaBaseProvider.graph", fake):
            msg = send_reply(conv, "hi")
        self.assertEqual(msg.status, "sent")
        self.assertEqual(calls, ["me/messages", "me/take_thread_control", "me/messages"])

    def test_clear_message_when_routing_disabled(self):
        from inbox.services import send_reply
        conv = self._channel()

        def fake(self_, method, path, token, **kw):
            raise HandoverTests._err(None, 2018300 if path == "me/messages" else 2018464)

        with mock.patch("integrations.providers.meta.MetaBaseProvider.graph", fake):
            msg = send_reply(conv, "hi")
        self.assertEqual(msg.status, "failed")
        self.assertIn("Conversation routing", msg.error)



class ExpiredTokenTests(TestCase):
    def test_expired_meta_token_gives_clear_message(self):
        from core.models import Workspace
        from integrations.sync import sync_channel
        ws = Workspace.objects.create(name="E")
        ch = ChannelAccount.objects.create(workspace=ws, provider="messenger", name="m", status="active",
                                           credentials={"page_id": "P", "page_access_token": "OLD", "app_secret": "s"})
        resp = mock.Mock(status_code=400, content=b"x")
        resp.json.return_value = {"error": {"message": "Session has expired", "type": "OAuthException", "code": 190}}
        with mock.patch("integrations.providers.base.requests.request", return_value=resp):
            sync_channel(ch)
        ch.refresh_from_db()
        self.assertEqual(ch.status, "error")
        self.assertIn("Token expiration: Never", ch.last_error)


class MobileInboxFilterTests(BaseAPITest):
    def test_kind_tabs_handoff_filter_and_last_direction(self):
        from core.models import Workspace
        from inbox.models import Conversation
        self.client.post("/api/channels/demo/")
        convs = list(Conversation.objects.filter(workspace_id=self.workspace_id).order_by("created_at"))
        comment, handed = convs[0], convs[1]
        comment.meta = {**comment.meta, "kind": "comment"}
        comment.save(update_fields=["meta"])
        handed.meta = {**handed.meta, "bot_paused": True, "bot_pause_reason": "handoff"}
        handed.save(update_fields=["meta"])
        total = self.client.get("/api/conversations/").data["count"]
        self.assertEqual(self.client.get("/api/conversations/?kind=comment").data["count"], 1)
        self.assertEqual(self.client.get("/api/conversations/?kind=message").data["count"], total - 1)
        handoff = self.client.get("/api/conversations/?ai=handoff").data["results"]
        self.assertEqual([c["id"] for c in handoff], [str(handed.id)])
        stats = self.client.get("/api/stats/").data
        self.assertEqual(stats["unread_by_kind"]["comment"], 1)
        self.assertEqual(stats["unread_by_kind"]["message"] + 1, stats["unread_conversations"])
        self.assertEqual(stats["ai_handoff"], 1)
        rows = self.client.get("/api/conversations/").data["results"]
        self.assertTrue(all(r["last_direction"] in ("in", "out") for r in rows))
        conv_id = rows[0]["id"]
        self.client.post(f"/api/conversations/{conv_id}/messages/", {"text": "Thanks!"}, format="json")
        Workspace.objects.all()  # noqa: B018
