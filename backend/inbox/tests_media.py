"""Photos, voice notes and files in conversations; instant updates."""
import hashlib
import hmac
import io
import json
import shutil
import subprocess
import tempfile
import threading
from unittest import mock, skipUnless

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from core import realtime
from integrations.models import ChannelAccount
from integrations.providers import IncomingMessage

from . import media
from .models import Attachment, Conversation, Message
from .services import ingest_message
from .tests import BaseAPITest

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
TMP_MEDIA = tempfile.mkdtemp()


class FakeResp:
    def __init__(self, content, ctype="image/jpeg", status=200):
        self.content, self.status_code, self.headers = content, status, {"Content-Type": ctype}

    def iter_content(self, n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class AttachmentTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        from core.models import Workspace
        self.ws = Workspace.objects.get(id=self.workspace_id)

    def upload(self, data=PNG, name="kurta.png", ctype="image/png", kind=""):
        body = {"file": SimpleUploadedFile(name, data, content_type=ctype)}
        if kind:
            body["kind"] = kind
        return self.client.post("/api/attachments/", body, format="multipart")

    def test_upload_and_send_photo_on_telegram(self):
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="Bot", status="active",
                                           credentials={"bot_token": "T", "mode": "polling"})
        conv_msg = ingest_message(ch, IncomingMessage(external_thread_id="42", contact_external_id="42", text="photo please",
                                                      external_message_id="1"))
        up = self.upload()
        self.assertEqual((up.status_code, up.data["kind"], up.data["mime"]), (201, "image", "image/png"))
        calls = []

        def fake_http(method, url, **kw):
            calls.append((url.rsplit("/", 1)[-1], kw.get("data"), list((kw.get("files") or {}).keys())))
            return {"ok": True, "result": {"message_id": 77}}
        with mock.patch("integrations.providers.base.BaseProvider.http", side_effect=fake_http):
            r = self.client.post(f"/api/conversations/{conv_msg.conversation_id}/messages/",
                                 {"text": "Here it is!", "attachment_ids": [up.data["id"]]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(calls, [("sendPhoto", {"chat_id": "42", "caption": "Here it is!"}, ["photo"])])
        self.assertEqual(r.data["attachments"][0]["kind"], "image")
        self.assertTrue(r.data["attachments"][0]["url"].startswith("/backend/attachments/"))
        self.assertEqual(Conversation.objects.get().last_message_preview, "Here it is!")
        # the file is used up: it can't be sent twice
        r2 = self.client.post(f"/api/conversations/{conv_msg.conversation_id}/messages/",
                              {"attachment_ids": [up.data["id"]]}, format="json")
        self.assertEqual(r2.status_code, 400)

    def test_unsupported_channel_and_other_workspace_files_are_refused(self):
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="tiktok", name="TT", status="active",
                                           credentials={"access_token": "x", "business_id": "b", "app_secret": "s"})
        m = ingest_message(ch, IncomingMessage(external_thread_id="c1", contact_external_id="u1", text="hi", external_message_id="1"))
        up = self.upload()
        r = self.client.post(f"/api/conversations/{m.conversation_id}/messages/", {"attachment_ids": [up.data["id"]]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("doesn't support", r.data["detail"])

    def test_incoming_whatsapp_photo_is_downloaded_and_served_safely(self):
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="whatsapp", name="WA", status="active",
                                           credentials={"access_token": "TOKEN", "phone_number_id": "PN", "app_secret": "sec"})
        body = json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PN"},
                           "contacts": [{"wa_id": "9779800000000", "profile": {"name": "Anita"}}],
                           "messages": [{"from": "9779800000000", "id": "wamid.1", "timestamp": "1790000000", "type": "image",
                                         "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "caption": "this one?"}}]}}]}]}).encode()
        sig = "sha256=" + hmac.new(b"sec", body, hashlib.sha256).hexdigest()
        with self.captureOnCommitCallbacks(execute=False):
            res = self.client.post(f"/api/webhooks/{ch.id}/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual(res.status_code, 200)
        att = Attachment.objects.get()
        self.assertEqual((att.status, att.kind, att.source), ("pending", "image", {"id": "MEDIA1"}))
        self.assertEqual(Message.objects.get().text, "this one?")
        with mock.patch("integrations.providers.base.BaseProvider.http", return_value={"url": "https://lookaside.fbsbx.com/x", "mime_type": "image/jpeg"}), \
                mock.patch("inbox.media.requests.get", return_value=FakeResp(JPEG)) as get:
            media.download(att.id)
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer TOKEN"})
        att.refresh_from_db()
        self.assertEqual((att.status, att.mime, att.size), ("ready", "image/jpeg", len(JPEG)))
        data = self.client.get(f"/api/conversations/{att.message.conversation_id}/messages/").data
        url = data[0]["attachments"][0]["url"].replace("/backend/", "/api/")
        anon = APIClient()
        resp = anon.get(url)  # signed link works without login
        self.assertEqual((resp.status_code, resp["Content-Type"]), (200, "image/jpeg"))
        self.assertIn("sandbox", resp["Content-Security-Policy"])
        self.assertEqual(anon.get(url[:-4] + "xxx-v/").status_code, 404)
        self.assertEqual(anon.get(url.replace(str(att.id), "00000000-0000-0000-0000-000000000000")).status_code, 404)

    def test_dangerous_types_always_download(self):
        up = self.upload(b"<svg onload=alert(1)>", "x.svg", "image/svg+xml")
        att = Attachment.objects.get(id=up.data["id"])
        resp = APIClient().get(f"/api/attachments/{att.id}/{media.token(att.id)}/")
        self.assertEqual(resp["Content-Type"], "application/octet-stream")
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_email_attachments_are_stored_from_the_message(self):
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="gmail", name="Mail", status="active",
                                           credentials={"email": "shop@example.com", "password": "p"})
        m = ingest_message(ch, IncomingMessage(external_thread_id="t", contact_external_id="a@b.com", text="invoice attached",
                                               external_message_id="<1@x>", attachments=[
                                                   {"type": "application/pdf", "mime": "application/pdf", "name": "bill.pdf",
                                                    "data": b"%PDF-1.4 test"}]))
        att = m.files.get()
        self.assertEqual((att.status, att.kind, att.name, att.mime), ("ready", "file", "bill.pdf", "application/pdf"))
        self.assertEqual(m.attachments, [{"type": "application/pdf", "name": "bill.pdf", "mime": "application/pdf"}])

    def test_attachment_only_message_preview(self):
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="viber", name="V", status="active",
                                           credentials={"auth_token": "t"})
        with self.captureOnCommitCallbacks(execute=False):
            ingest_message(ch, IncomingMessage(external_thread_id="v1", contact_external_id="v1", external_message_id="1",
                                               attachments=[{"type": "picture", "url": "https://dl-media.viber.com/x.jpg"}]))
        self.assertEqual(Conversation.objects.get().last_message_preview, "📷 Photo")

    @skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_voice_note_is_converted_to_ogg_opus(self):
        webm = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                               "-c:a", "libopus", "-f", "webm", "-"], capture_output=True, check=True).stdout
        up = self.upload(webm, "recording.webm", "audio/webm", kind="voice")
        self.assertEqual((up.status_code, up.data["kind"], up.data["mime"]), (201, "voice", "audio/ogg"))

    def test_widget_visitor_can_send_a_photo_but_not_other_files(self):
        res = self.client.post("/api/channels/", {"provider": "website", "name": "Site", "credentials": {"title": "Chat"}}, format="json")
        cid = res.data["id"]
        anon = APIClient()
        token = anon.post(f"/api/widget/{cid}/session/", {}, format="json").data["token"]
        bad = anon.post(f"/api/widget/{cid}/upload/", {"file": SimpleUploadedFile("x.html", b"<html>", content_type="image/png")},
                        format="multipart", HTTP_X_VISITOR_TOKEN=token)
        self.assertEqual(bad.status_code, 400)
        ok = anon.post(f"/api/widget/{cid}/upload/", {"file": SimpleUploadedFile("shot.png", PNG, content_type="image/png"),
                                                      "text": "this colour"}, format="multipart", HTTP_X_VISITOR_TOKEN=token)
        self.assertEqual(ok.status_code, 201)
        msgs = anon.get(f"/api/widget/{cid}/messages/", HTTP_X_VISITOR_TOKEN=token).data
        self.assertEqual((msgs[0]["text"], msgs[0]["files"][0]["kind"]), ("this colour", "image"))


class RealtimeTests(BaseAPITest):
    def test_events_return_when_something_changes(self):
        first = self.client.get("/api/events/").data
        self.assertFalse(first["changed"])
        self.client.post("/api/channels/demo/")  # creates conversations -> bumps the workspace
        with mock.patch.object(realtime, "WAIT_SECONDS", 1):
            second = self.client.get("/api/events/", {"v": first["v"]}).data
        self.assertTrue(second["changed"])
        self.assertNotEqual(second["v"], first["v"])

    def test_wait_wakes_up_on_bump(self):
        v = realtime.current(self.workspace_id)
        timer = threading.Timer(0.5, lambda: realtime.cache.incr(realtime._key(self.workspace_id)))
        timer.start()
        new_v, changed = realtime.wait(self.workspace_id, v, timeout=5)
        self.assertTrue(changed)
        timer.cancel()
