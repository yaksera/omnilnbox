import time
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Workspace
from publishing.models import Post, SocialAccount
from publishing.platforms.base import Publisher
from publishing.services import publish_due, publish_post

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 400


def register(client, email="owner@example.com"):
    res = client.post("/api/auth/register/", {"name": "Owner One", "email": email, "password": "Kathmandu-Blue-42"},
                      format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")


class FakeResp:
    def __init__(self, headers=None):
        self.headers = headers or {}


def fake_http(calls):
    def http(method, url, **kw):
        calls.append((method, url.split("?")[0]))
        u = url
        if "graph.facebook.com" in u:
            if u.endswith("/me/accounts"):
                return FakeResp(), {"data": [{"id": "PAGE1", "name": "My Shop", "access_token": "PAGE_TOKEN",
                                              "instagram_business_account": {"id": "IG1", "username": "myshop"}}]}
            if u.endswith("/PAGE1/photos"):
                return FakeResp(), {"id": "PHOTO1", "post_id": "PAGE1_POST1"}
            if u.endswith("/IG1/media"):
                return FakeResp(), {"id": "CONTAINER1"}
            if u.endswith("/CONTAINER1"):
                return FakeResp(), {"status_code": "FINISHED"}
            if u.endswith("/IG1/media_publish"):
                return FakeResp(), {"id": "IGMEDIA1"}
            if u.endswith("/IGMEDIA1"):
                return FakeResp(), {"permalink": "https://instagram.com/p/abc"}
        if "upload/youtube" in u:
            return FakeResp({"Location": "https://upload.example/session1"}), {}
        if u == "https://upload.example/session1":
            return FakeResp(), {"id": "YT123"}
        if "open.tiktokapis.com" in u:
            if u.endswith("/creator_info/query/"):
                return FakeResp(), {"data": {"privacy_level_options": ["SELF_ONLY"]}, "error": {"code": "ok"}}
            if u.endswith("/video/init/"):
                return FakeResp(), {"data": {"publish_id": "PUB1", "upload_url": "https://tt-upload.example/1"},
                                    "error": {"code": "ok"}}
            if u.endswith("/status/fetch/"):
                return FakeResp(), {"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}}
        if u == "https://tt-upload.example/1":
            return FakeResp(), {}
        raise AssertionError(f"unexpected call {method} {u}")
    return http


@override_settings(MEDIA_ROOT="/tmp/omni-test-media")
class PublishingBase(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()
        register(self.c)
        self.ws = Workspace.objects.get()
        self.calls = []

    def patch(self):
        return mock.patch.object(Publisher, "http", staticmethod(fake_http(self.calls)))

    def upload(self, data=JPEG, name="photo.jpg"):
        return self.c.post("/api/publishing/media/", {"file": SimpleUploadedFile(name, data)}, format="multipart")

    def connect_meta(self):
        with self.patch():
            return self.c.post("/api/publishing/accounts/facebook/", {"access_token": "SYSUSER"}, format="json")

    def add_video_accounts(self):
        yt = SocialAccount.objects.create(workspace=self.ws, platform="youtube", external_id="UC1", name="My Channel",
                                          credentials={"access_token": "A", "expires_at": int(time.time()) + 3600})
        tt = SocialAccount.objects.create(workspace=self.ws, platform="tiktok", external_id="OPEN1", name="myshop",
                                          credentials={"access_token": "A", "expires_at": int(time.time()) + 3600})
        return yt, tt



class PublishingTests(PublishingBase):
    def test_connect_facebook_also_connects_linked_instagram(self):
        res = self.connect_meta()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(sorted(a["platform"] for a in res.data["accounts"]), ["facebook", "instagram"])
        acc = SocialAccount.objects.get(platform="facebook")
        self.assertEqual(acc.credentials["page_token"], "PAGE_TOKEN")  # encrypted at rest, decrypted here

    @override_settings(META_APP_ID="111", META_APP_SECRET="sec", META_PAGES_CONFIG_ID="cfg1")
    def test_continue_with_facebook_checks_permissions_and_makes_token_permanent(self):
        self.assertEqual(self.c.get("/api/publishing/config/").data["facebook_login"]["config_id"], "cfg1")
        seen = []

        def graph(method, url, params=None, **kw):
            path = url.split("v21.0/", 1)[1]
            seen.append(path)
            body = {"debug_token": {"data": {"is_valid": True, "app_id": "111", "scopes":
                    ["pages_show_list", "pages_manage_posts"] if params.get("input_token") == "GOOD" else ["pages_messaging"]}},
                    "oauth/access_token": {"access_token": "LONG"}}[path]
            r = mock.Mock(status_code=200, text="{}")
            r.json.return_value = body
            return r
        with mock.patch("integrations.meta_connect.requests.request", side_effect=graph):
            weak = self.c.post("/api/publishing/accounts/facebook/", {"access_token": "WEAK", "via": "facebook_login"},
                               format="json")
            with self.patch():
                ok = self.c.post("/api/publishing/accounts/facebook/", {"access_token": "GOOD", "via": "facebook_login"},
                                 format="json")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("pages_manage_posts", weak.data["detail"])
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertIn("oauth/access_token", seen)  # exchanged for a long-lived token before fetching Page tokens
        self.assertEqual(SocialAccount.objects.get(platform="facebook").credentials["page_token"], "PAGE_TOKEN")

    def test_media_upload_sniffs_type_and_serves_only_signed_links(self):
        bad = self.upload(b"MZ\x90\x00 not an image", "evil.jpg")
        self.assertEqual(bad.status_code, 400)
        ok = self.upload()
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(ok.data["mime"], "image/jpeg")
        path = ok.data["preview_url"].replace("/backend/", "/api/")
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/api/publishing/files/forged-token/").status_code, 404)

    def test_platform_rules_are_validated(self):
        self.connect_meta()
        yt, tt = self.add_video_accounts()
        img = self.upload().data["id"]
        res = self.c.post("/api/publishing/posts/", {"caption": "Hi", "media_id": img, "action": "publish",
                                                     "targets": [{"account_id": str(tt.id)}, {"account_id": str(yt.id)}]},
                          format="json")
        self.assertEqual(res.status_code, 400)
        msg = str(res.data)
        self.assertIn("TikTok", msg)
        self.assertIn("YouTube needs a video title", msg)

    def test_publish_to_all_four_platforms(self):
        self.connect_meta()
        yt, tt = self.add_video_accounts()
        fb = SocialAccount.objects.get(platform="facebook")
        ig = SocialAccount.objects.get(platform="instagram")
        img = self.upload().data["id"]
        vid = self.upload(MP4, "clip.mp4").data["id"]
        with self.patch():
            p1 = self.c.post("/api/publishing/posts/", {"caption": "New arrivals!", "media_id": img, "action": "publish",
                                                        "targets": [{"account_id": str(fb.id)}, {"account_id": str(ig.id)}]},
                             format="json")
            p2 = self.c.post("/api/publishing/posts/", {"caption": "Behind the scenes", "media_id": vid, "action": "publish",
                                                        "targets": [{"account_id": str(yt.id), "options": {"title": "BTS", "privacy": "unlisted"}},
                                                                    {"account_id": str(tt.id), "options": {"privacy": "SELF_ONLY"}}]}, format="json")
            self.assertEqual(p1.status_code, 201, p1.data)
            self.assertEqual(p2.status_code, 201, p2.data)
            publish_post(p1.data["id"])  # the background thread doesn't run inside test transactions
            publish_post(p2.data["id"])
        post1 = self.c.get(f"/api/publishing/posts/{p1.data['id']}/").data
        post2 = self.c.get(f"/api/publishing/posts/{p2.data['id']}/").data
        self.assertEqual(post1["status"], "published")
        self.assertEqual(post2["status"], "published")
        urls = {t["account"]["platform"]: t["url"] for t in post1["targets"] + post2["targets"]}
        self.assertEqual(urls["facebook"], "https://www.facebook.com/PAGE1_POST1")
        self.assertEqual(urls["instagram"], "https://instagram.com/p/abc")
        self.assertEqual(urls["youtube"], "https://youtu.be/YT123")
        tt_target = next(t for t in post2["targets"] if t["account"]["platform"] == "tiktok")
        self.assertIn("SELF_ONLY", tt_target["options"]["note"])  # unaudited TikTok apps post privately

    def test_scheduling_and_no_double_publish(self):
        self.connect_meta()
        fb = SocialAccount.objects.get(platform="facebook")
        when = (timezone.now() + timedelta(hours=2)).isoformat()
        res = self.c.post("/api/publishing/posts/", {"caption": "Tomorrow's offer", "action": "schedule", "scheduled_at": when,
                                                     "targets": [{"account_id": str(fb.id)}]}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(publish_due(), 0)  # not due yet
        Post.objects.update(scheduled_at=timezone.now() - timedelta(minutes=1))
        with mock.patch.object(Publisher, "http", staticmethod(lambda m, u, **k: (FakeResp(), {"id": "PAGE1_77"}))):
            self.assertEqual(publish_due(), 1)
            self.assertEqual(publish_due(), 0)  # already claimed/published
        self.assertEqual(Post.objects.get().status, "published")

    def test_partial_failure_and_retry(self):
        self.connect_meta()
        fb, ig = SocialAccount.objects.get(platform="facebook"), SocialAccount.objects.get(platform="instagram")
        img = self.upload().data["id"]
        res = self.c.post("/api/publishing/posts/", {"caption": "x", "media_id": img, "action": "publish",
                                                     "targets": [{"account_id": str(fb.id)}, {"account_id": str(ig.id)}]},
                          format="json")

        def flaky(method, url, **kw):
            if "/IG1/" in url:
                from publishing.platforms.base import PublishError
                raise PublishError("400: media fetch failed")
            return FakeResp(), {"id": "OK1", "post_id": "PAGE1_OK"}

        with mock.patch.object(Publisher, "http", staticmethod(flaky)):
            publish_post(res.data["id"])
        self.assertEqual(Post.objects.get().status, "partial")
        with mock.patch("publishing.views.publish_in_background"):
            self.assertEqual(self.c.post(f"/api/publishing/posts/{res.data['id']}/retry/").status_code, 200)
        with self.patch():
            publish_post(res.data["id"])
        self.assertEqual(Post.objects.get().status, "published")

    def test_roles_and_plan_gating(self):
        self.connect_meta()
        fb = SocialAccount.objects.get(platform="facebook")
        inv = self.c.post("/api/team/", {"email": "agent@example.com", "role": "agent"}, format="json").data
        token = inv["url"].rsplit("/", 1)[1]
        APIClient().post(f"/api/invites/{token}/", {"name": "Agent A", "password": "Kathmandu-Blue-42"}, format="json")
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION="Bearer " + agent.post(
            "/api/auth/login/", {"email": "agent@example.com", "password": "Kathmandu-Blue-42"}, format="json").data["access"])
        body = {"caption": "Draft by agent", "targets": [{"account_id": str(fb.id)}]}
        self.assertEqual(agent.post("/api/publishing/posts/", {**body, "action": "draft"}, format="json").status_code, 201)
        self.assertEqual(agent.post("/api/publishing/posts/", {**body, "action": "publish"}, format="json").status_code, 403)
        self.assertEqual(agent.post("/api/publishing/accounts/facebook/", {"access_token": "x"}, format="json").status_code, 403)
        # Starter can publish but not schedule; Free can't publish at all
        Workspace.objects.update(plan="starter", trial_ends_at=None, plan_expires_at=timezone.now() + timedelta(days=30))
        when = (timezone.now() + timedelta(hours=1)).isoformat()
        self.assertEqual(self.c.post("/api/publishing/posts/", {**body, "action": "schedule", "scheduled_at": when},
                                     format="json").status_code, 402)
        Workspace.objects.update(plan="free", plan_expires_at=None)
        self.assertEqual(self.upload().status_code, 402)

    def test_oauth_not_configured_and_bad_state(self):
        self.assertEqual(self.c.post("/api/publishing/oauth/youtube/start/").status_code, 400)
        r = self.client.get("/api/publishing/oauth/tiktok/callback/", {"state": "forged", "code": "x"})
        self.assertIn("connected=error", r["Location"])

    @override_settings(GOOGLE_CLIENT_ID="gid", GOOGLE_CLIENT_SECRET="gsec")
    def test_youtube_oauth_start_url(self):
        url = self.c.post("/api/publishing/oauth/youtube/start/").data["url"]
        self.assertIn("accounts.google.com", url)
        self.assertIn("youtube.upload", url)
        self.assertIn("access_type=offline", url)
