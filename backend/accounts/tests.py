import re
from datetime import timedelta
from unittest import mock

from cryptography.hazmat.primitives.asymmetric import ec
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Workspace
from inbox.models import Conversation
from inbox.services import ingest_message
from integrations.models import ChannelAccount
from integrations.providers import IncomingMessage

from . import notify, totp, webpush
from .models import AuditLog, Profile, PushSubscription

PASSWORD = "Kathmandu-Blue-42"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", EMAIL_HOST="smtp.test",
                   FRONTEND_URL="http://app.test")
class AccountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()
        res = self.c.post("/api/auth/register/", {"name": "Sita Sharma", "email": "sita@example.com", "password": PASSWORD},
                          format="json")
        self.c.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.ws = Workspace.objects.get()

    def link(self, pattern):
        body = mail.outbox[-1].body
        return re.search(pattern, body).group(1)

    def test_register_sends_verification_and_verify_works(self):
        self.assertIn("Confirm your email", mail.outbox[0].subject)
        self.assertFalse(self.c.get("/api/auth/me/").data["user"]["email_verified"])
        token = self.link(r"verify-email\?token=(\S+)")
        self.assertEqual(APIClient().post("/api/auth/email/verify/", {"token": token}, format="json").status_code, 200)
        self.assertTrue(self.c.get("/api/auth/me/").data["user"]["email_verified"])
        self.assertEqual(APIClient().post("/api/auth/email/verify/", {"token": token + "x"}, format="json").status_code, 400)

    def test_logout_and_logout_all_devices(self):
        anon = APIClient()
        login = lambda: anon.post("/api/auth/login/", {"email": "sita@example.com", "password": PASSWORD}, format="json").data["refresh"]
        phone, laptop = login(), login()
        # normal logout revokes only that session
        self.assertEqual(anon.post("/api/auth/logout/", {"refresh": phone}, format="json").status_code, 205)
        self.assertEqual(anon.post("/api/auth/refresh/", {"refresh": phone}, format="json").status_code, 401)
        self.assertEqual(anon.post("/api/auth/refresh/", {"refresh": laptop}, format="json").status_code, 200)
        # logout everywhere needs a signed-in user and revokes every session
        self.assertEqual(anon.post("/api/auth/logout-all/").status_code, 401)
        tablet = login()
        self.assertEqual(self.c.get("/api/auth/me/").status_code, 200)
        later = timezone.now() + timedelta(seconds=2)  # tokens above were issued "before" the revoke
        with mock.patch("accounts.views.timezone.now", return_value=later):
            self.assertEqual(self.c.post("/api/auth/logout-all/").status_code, 200)
        self.assertEqual(anon.post("/api/auth/refresh/", {"refresh": tablet}, format="json").status_code, 401)
        self.assertEqual(self.c.get("/api/auth/me/").status_code, 401)  # access tokens stop working immediately too
        Profile.objects.update(sessions_revoked_at=timezone.now() - timedelta(seconds=5))  # time passes...
        fresh = anon.post("/api/auth/login/", {"email": "sita@example.com", "password": PASSWORD}, format="json").data["access"]
        self.assertEqual(APIClient(HTTP_AUTHORIZATION=f"Bearer {fresh}").get("/api/auth/me/").status_code, 200)  # new logins work
        self.assertTrue(AuditLog.objects.filter(action="auth.logout_all").exists())

    def test_password_reset_flow_logs_out_everywhere(self):
        anon = APIClient()
        old_refresh = anon.post("/api/auth/login/", {"email": "sita@example.com", "password": PASSWORD}, format="json").data["refresh"]
        r = anon.post("/api/auth/password/forgot/", {"email": "nobody@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)  # same answer for unknown emails
        n = len(mail.outbox)
        anon.post("/api/auth/password/forgot/", {"email": "SITA@example.com"}, format="json")
        self.assertEqual(len(mail.outbox), n + 1)
        uid, token = re.search(r"uid=(\w+)&token=([\w-]+)", mail.outbox[-1].body).groups()
        self.assertEqual(anon.post("/api/auth/password/reset/", {"uid": uid, "token": token, "password": "short"},
                                   format="json").status_code, 400)
        self.assertEqual(anon.post("/api/auth/password/reset/", {"uid": uid, "token": token, "password": "New-Pokhara-77"},
                                   format="json").status_code, 200)
        # link works once; old sessions are revoked; new password works
        self.assertEqual(anon.post("/api/auth/password/reset/", {"uid": uid, "token": token, "password": "Another-Pass-88"},
                                   format="json").status_code, 400)
        self.assertEqual(anon.post("/api/auth/refresh/", {"refresh": old_refresh}, format="json").status_code, 401)
        self.assertEqual(anon.post("/api/auth/login/", {"email": "sita@example.com", "password": "New-Pokhara-77"},
                                   format="json").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="auth.password_reset").exists())

    def test_two_factor_login_with_code_and_recovery_code(self):
        setup = self.c.post("/api/auth/2fa/setup/").data
        self.assertIn("<svg", setup["qr_svg"])
        self.assertEqual(self.c.post("/api/auth/2fa/enable/", {"code": "000000"}, format="json").status_code, 400)
        codes = self.c.post("/api/auth/2fa/enable/", {"code": totp.now_code(setup["secret"])}, format="json").data["recovery_codes"]
        self.assertEqual(len(codes), 10)
        anon = APIClient()
        step1 = anon.post("/api/auth/login/", {"email": "sita@example.com", "password": PASSWORD}, format="json").data
        self.assertTrue(step1["two_factor_required"])
        self.assertNotIn("access", step1)
        self.assertEqual(anon.post("/api/auth/2fa/login/", {"ticket": step1["ticket"], "code": "123456"}, format="json").status_code, 400)
        ok = anon.post("/api/auth/2fa/login/", {"ticket": step1["ticket"], "code": totp.now_code(setup["secret"])}, format="json")
        self.assertIn("access", ok.data)
        # recovery code works once
        self.assertIn("access", anon.post("/api/auth/2fa/login/", {"ticket": step1["ticket"], "code": codes[0]}, format="json").data)
        self.assertEqual(anon.post("/api/auth/2fa/login/", {"ticket": step1["ticket"], "code": codes[0]}, format="json").status_code, 400)
        self.assertEqual(self.c.post("/api/auth/2fa/disable/", {"password": "wrong"}, format="json").status_code, 400)
        self.assertEqual(self.c.post("/api/auth/2fa/disable/", {"password": PASSWORD}, format="json").status_code, 200)
        self.assertIn("access", anon.post("/api/auth/login/", {"email": "sita@example.com", "password": PASSWORD}, format="json").data)

    def test_push_notification_is_encrypted_for_the_device(self):
        device = ec.generate_private_key(ec.SECP256R1())
        auth = webpush.b64u(b"0123456789abcdef")
        p256dh = webpush.b64u(webpush._raw_public(device))
        self.assertEqual(self.c.post("/api/notifications/push/subscribe/", {
            "endpoint": "https://push.example/abc", "keys": {"p256dh": p256dh, "auth": auth}}, format="json").status_code, 201)
        self.assertTrue(self.c.get("/api/notifications/push/key/").data["public_key"])
        channel = ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="Bot", status="active")
        msg = ingest_message(channel, IncomingMessage(external_thread_id="1", contact_external_id="1", contact_name="Ram",
                                                      text="Is the red kurta in stock?", external_message_id="m1"))
        sent = []
        with mock.patch("accounts.webpush.requests.post", side_effect=lambda url, **kw: sent.append(kw) or mock.Mock(status_code=201)):
            self.assertEqual(notify.push_incoming(msg.id), 1)
            self.assertEqual(notify.push_incoming(msg.id), 0)  # throttled per conversation
        body = webpush.decrypt(sent[0]["data"], device, auth)
        self.assertIn(b"Is the red kurta in stock?", body)
        self.assertTrue(sent[0]["headers"]["Authorization"].startswith("vapid t="))
        with mock.patch("accounts.webpush.requests.post", return_value=mock.Mock(status_code=410)):
            cache.clear()
            notify.push_incoming(msg.id)
        self.assertFalse(PushSubscription.objects.exists())  # expired subscriptions are removed

    def test_unanswered_alert_email_once(self):
        channel = ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="Bot", status="active")
        ingest_message(channel, IncomingMessage(external_thread_id="1", contact_external_id="1", contact_name="Ram",
                                                text="hello?", external_message_id="m1",
                                                sent_at=timezone.now() - timedelta(minutes=45)))
        n = len(mail.outbox)
        self.assertEqual(notify.unanswered_alerts(), 1)
        self.assertIn("waiting", mail.outbox[-1].subject)
        self.assertIn("Ram", mail.outbox[-1].body)
        self.assertEqual(notify.unanswered_alerts(), 0)  # not again for the same message
        self.assertEqual(len(mail.outbox), n + 1)
        self.c.put("/api/notifications/prefs/", {"email_unanswered": False}, format="json")
        self.assertFalse(Profile.objects.get(user__email="sita@example.com").notify_email_unanswered)
        Conversation.objects.update(meta={})
        self.assertEqual(notify.unanswered_alerts(), 0)

    def test_audit_log_is_business_only_and_records_actions(self):
        self.c.post("/api/team/", {"email": "agent@example.com", "role": "agent"}, format="json")
        self.assertEqual(self.c.get("/api/audit-log/").status_code, 402)  # Pro trial
        Workspace.objects.update(plan="business", trial_ends_at=None, plan_expires_at=timezone.now() + timedelta(days=30))
        rows = self.c.get("/api/audit-log/").data["results"]
        self.assertEqual(rows[0]["action"], "team.invited")
        self.assertEqual(rows[0]["target"], "agent@example.com")

    def test_onboarding_checklist(self):
        data = self.c.get("/api/onboarding/").data
        keys = [s["key"] for s in data["steps"]]
        self.assertIn("connect_channel", keys)
        self.assertEqual(data["done"], 0)
        ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="Bot", status="active")
        done = {s["key"]: s["done"] for s in self.c.get("/api/onboarding/").data["steps"]}
        self.assertTrue(done["connect_channel"])
        self.assertTrue(self.c.post("/api/onboarding/", {"dismissed": True}, format="json").data["dismissed"])


class TotpTests(TestCase):
    def test_rfc6238_vector(self):
        import base64
        secret = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(totp._code(secret, 59 // 30), "287082")
        self.assertEqual(totp._code(secret, 1111111109 // 30), "081804")

    def test_rfc8291_vector(self):
        priv = ec.derive_private_key(int.from_bytes(webpush.unb64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
                                     ec.SECP256R1())
        body = webpush.encrypt(b"When I grow up, I want to be a watermelon",
                               "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                               "BTBZMqHH6r4Tts7J_aSIgg", salt=webpush.unb64u("DGv6ra1nlYgDCS1FRnbzlw"), server_key=priv)
        self.assertEqual(webpush.b64u(body), "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLo"
                                             "cInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouB"
                                             "WLVWGNWQexSgSxsj_Qulcy4a-fN")
