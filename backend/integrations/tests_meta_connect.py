"""One-click Connect with Facebook (WhatsApp Embedded Signup, Pages + Instagram) and the shared Meta webhook."""
import hashlib
import hmac
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from inbox.models import Conversation, Message

from .models import ChannelAccount

META = dict(META_APP_ID="111", META_APP_SECRET="appsecret", META_VERIFY_TOKEN="vt", META_WA_CONFIG_ID="wa-cfg",
            META_PAGES_CONFIG_ID="pages-cfg")


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self._data


def fake_graph(calls):
    def request(method, url, params=None, headers=None, timeout=None, json=None):
        path = url.split("v21.0/", 1)[1]
        calls.append((method, path, json))
        if path == "oauth/access_token":
            return Resp({"access_token": "LONG-USER" if (params or {}).get("grant_type") else "BIZ-TOKEN"})
        if path == "PN1":
            return Resp({"display_phone_number": "+977 980-0000000", "verified_name": "Sita Kurta"})
        if path.endswith("subscribed_apps"):
            return Resp({"success": True})
        if path == "PN1/register":
            return Resp({"success": True})
        if path == "debug_token" and params["input_token"] == "BIZ-TOKEN":
            return Resp({"data": {"is_valid": True, "app_id": "111", "granular_scopes": [
                {"scope": "whatsapp_business_management", "target_ids": ["WABA1"]},
                {"scope": "whatsapp_business_messaging", "target_ids": ["WABA1"]}]}})
        if path == "WABA1/phone_numbers":
            return Resp({"data": [{"id": "PN1"}]})
        if path == "debug_token":
            ok = params["input_token"] == "SDK-USER-TOKEN"
            return Resp({"data": {"is_valid": ok, "app_id": "111" if ok else "999"}})
        if path == "me/accounts":
            return Resp({"data": [
                {"id": "PAGE1", "name": "Sita Kurta Page", "access_token": "PAGE-TOKEN",
                 "instagram_business_account": {"id": "IG1", "username": "sitakurta"}},
                {"id": "PAGE2", "name": "Other Page", "access_token": "PAGE2-TOKEN"}]})
        if path == "IG1":
            return Resp({"id": "IG1", "username": "sitakurta"})
        return Resp({"error": {"message": f"unexpected {path}"}}, 400)
    return request


@override_settings(**META)
class MetaConnectTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()
        r = self.c.post("/api/auth/register/", {"name": "Sita", "email": "sita@example.com", "password": "Kathmandu-Blue-42"},
                        format="json")
        self.c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    def test_config_says_what_is_enabled(self):
        data = self.c.get("/api/meta/config/").data
        self.assertEqual((data["app_id"], data["whatsapp"]["enabled"], data["pages"]["config_id"]), ("111", True, "pages-cfg"))
        with override_settings(META_WA_CONFIG_ID=""):
            self.assertFalse(self.c.get("/api/meta/config/").data["whatsapp"]["enabled"])

    def test_whatsapp_embedded_signup_creates_a_ready_channel(self):
        calls = []
        with mock.patch("integrations.meta_connect.requests.request", side_effect=fake_graph(calls)):
            r = self.c.post("/api/meta/whatsapp/", {"code": "CODE", "waba_id": "WABA1", "phone_number_id": "PN1", "pin": "123456"},
                            format="json")
        self.assertEqual(r.status_code, 201, r.data)
        ch = ChannelAccount.objects.get(provider="whatsapp")
        self.assertEqual((ch.name, ch.status, ch.state["meta_id"]), ("Sita Kurta", "active", "PN1"))
        self.assertEqual(ch.credentials["access_token"], "BIZ-TOKEN")
        self.assertEqual(ch.credentials["business_account_id"], "WABA1")
        self.assertIn(("POST", "WABA1/subscribed_apps", None), calls)
        self.assertIn(("POST", "PN1/register", {"messaging_product": "whatsapp", "pin": "123456"}), calls)
        self.assertNotIn("BIZ-TOKEN", json.dumps(r.data))  # tokens never go back to the browser

    def test_pages_flow_lists_then_connects_selected_pages_and_instagram(self):
        calls = []
        with mock.patch("integrations.meta_connect.requests.request", side_effect=fake_graph(calls)):
            listed = self.c.post("/api/meta/pages/", {"code": "CODE"}, format="json")
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual([p["id"] for p in listed.data["pages"]], ["PAGE1", "PAGE2"])
        self.assertEqual(listed.data["pages"][0]["instagram"]["username"], "sitakurta")
        self.assertNotIn("PAGE-TOKEN", json.dumps(listed.data))
        with mock.patch("integrations.providers.base.BaseProvider.http", side_effect=lambda m, u, **k:
                        {"data": []} if "me/accounts" in u else {"success": True} if "subscribed_apps" in u
                        else {"id": "IG1", "username": "sitakurta"}):
            r = self.c.post("/api/meta/pages/connect/", {"session": listed.data["session"], "pages": ["PAGE1"],
                                                         "instagram": ["IG1"]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        msgr = ChannelAccount.objects.get(provider="messenger")
        ig = ChannelAccount.objects.get(provider="instagram")
        self.assertEqual((msgr.credentials["page_id"], msgr.credentials["page_access_token"], msgr.state["meta_id"]),
                         ("PAGE1", "PAGE-TOKEN", "PAGE1"))
        self.assertEqual((ig.name, ig.credentials["ig_account_id"]), ("@sitakurta", "IG1"))
        # the session is single-use
        again = self.c.post("/api/meta/pages/connect/", {"session": listed.data["session"], "pages": ["PAGE2"]}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_whatsapp_number_found_from_token_when_popup_did_not_say(self):
        calls = []
        with mock.patch("integrations.meta_connect.requests.request", side_effect=fake_graph(calls)):
            r = self.c.post("/api/meta/whatsapp/", {"code": "CODE", "waba_id": "", "phone_number_id": "", "pin": "123456"},
                            format="json")
        self.assertEqual(r.status_code, 201, r.data)
        ch = ChannelAccount.objects.get(provider="whatsapp")
        self.assertEqual((ch.credentials["phone_number_id"], ch.credentials["business_account_id"]), ("PN1", "WABA1"))
        self.assertIn(("POST", "WABA1/subscribed_apps", None), calls)

    def test_pages_with_sdk_access_token_is_verified_for_our_app(self):
        calls = []
        with mock.patch("integrations.meta_connect.requests.request", side_effect=fake_graph(calls)):
            ok = self.c.post("/api/meta/pages/", {"access_token": "SDK-USER-TOKEN"}, format="json")
            bad = self.c.post("/api/meta/pages/", {"access_token": "TOKEN-FROM-ANOTHER-APP"}, format="json")
            none = self.c.post("/api/meta/pages/", {}, format="json")
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual([p["id"] for p in ok.data["pages"]], ["PAGE1", "PAGE2"])
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(none.status_code, 400)
        self.assertEqual(sum(1 for c in calls if c[1] == "me/accounts"), 1)  # the foreign token never got further

    def test_channel_limit_applies(self):
        from core.models import Workspace
        Workspace.objects.update(plan="free", trial_ends_at=None, plan_expires_at=None)
        for i in range(2):
            ChannelAccount.objects.create(workspace=Workspace.objects.get(), provider="telegram", name=f"b{i}", status="active")
        with mock.patch("integrations.meta_connect.requests.request", side_effect=fake_graph([])):
            r = self.c.post("/api/meta/whatsapp/", {"code": "CODE", "waba_id": "WABA1", "phone_number_id": "PN1"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("allows 2 channels", str(r.data))

    def test_shared_webhook_routes_messages_to_the_right_workspace(self):
        with mock.patch("integrations.meta_connect.requests.request", side_effect=fake_graph([])):
            self.c.post("/api/meta/whatsapp/", {"code": "CODE", "waba_id": "WABA1", "phone_number_id": "PN1"}, format="json")
        anon = APIClient()
        ok = anon.get("/api/webhooks/meta/", {"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"})
        self.assertEqual(ok.content, b"42")
        self.assertEqual(anon.get("/api/webhooks/meta/", {"hub.mode": "subscribe", "hub.verify_token": "no"}).status_code, 403)
        body = json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "WABA1", "changes": [{"value": {
            "metadata": {"phone_number_id": "PN1"}, "contacts": [{"wa_id": "9779811111111", "profile": {"name": "Hari"}}],
            "messages": [{"from": "9779811111111", "id": "wamid.X", "timestamp": "1790000000", "type": "text",
                          "text": {"body": "Namaste, price?"}}]}}]},
            {"id": "WABA9", "changes": [{"value": {"metadata": {"phone_number_id": "UNKNOWN"}, "messages": [
                {"from": "1", "id": "wamid.Y", "timestamp": "1790000000", "type": "text", "text": {"body": "lost"}}]}}]}]}).encode()
        bad = anon.post("/api/webhooks/meta/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=00")
        self.assertEqual(bad.status_code, 403)
        sig = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
        r = anon.post("/api/webhooks/meta/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual(r.json()["stored"], 1)
        self.assertEqual(list(Message.objects.values_list("text", flat=True)), ["Namaste, price?"])
        self.assertEqual(Conversation.objects.get().contact.name, "Hari")

    def test_older_pasted_token_channels_are_found_by_their_id(self):
        from core.models import Workspace
        ch = ChannelAccount.objects.create(workspace=Workspace.objects.get(), provider="messenger", name="Page", status="active",
                                           credentials={"page_id": "PAGE7", "page_access_token": "T", "app_secret": "x"})
        body = json.dumps({"object": "page", "entry": [{"id": "PAGE7", "messaging": [{
            "sender": {"id": "U1"}, "recipient": {"id": "PAGE7"}, "timestamp": 1790000000000,
            "message": {"mid": "m1", "text": "hello"}}]}]}).encode()
        sig = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
        with mock.patch("integrations.providers.base.BaseProvider.http", return_value={"name": "Ram"}):
            r = APIClient().post("/api/webhooks/meta/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual(r.json()["stored"], 1)
        ch.refresh_from_db()
        self.assertEqual(ch.state["meta_id"], "PAGE7")


class StandbyTests(TestCase):
    """Messages Meta sends as 'standby' (another app controls the thread) still reach the inbox."""

    def test_standby_event_is_parsed_like_a_message(self):
        from core.models import Workspace
        from integrations.providers import get_provider
        ws = Workspace.objects.create(name="S", slug="s")
        ch = ChannelAccount.objects.create(workspace=ws, provider="messenger", name="P",
                                           credentials={"page_id": "PAGE1", "page_access_token": "t"})
        body = json.dumps({"object": "page", "entry": [{"id": "PAGE1", "standby": [
            {"sender": {"id": "U1"}, "recipient": {"id": "PAGE1"}, "timestamp": 1790000000000,
             "message": {"mid": "m.sb", "text": "price?"}}]}]}).encode()

        class R:
            pass
        req = R(); req.body = body
        with mock.patch("integrations.providers.meta._MessagingPlatformProvider._profile", return_value={"name": "Ram"}):
            items = get_provider(ch).parse_webhook(req)
        self.assertEqual([(i.text, i.direction, i.external_thread_id) for i in items], [("price?", "in", "U1")])

