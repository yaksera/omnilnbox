"""Smart publisher: per-platform settings reach each API, video checks, TikTok creator info, AI fill."""
import json
import shutil
import subprocess
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from publishing.models import MediaAsset, SocialAccount
from publishing.platforms.base import Publisher, clean_options, validate_target
from publishing.services import publish_post

from .tests import FakeResp, PublishingBase


def make_video(seconds=4, size="320x568"):
    """A real tiny MP4 made with ffmpeg (None when ffmpeg isn't installed)."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = f"{tmp}/v.mp4"
        subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=10",
                        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out], check=True, capture_output=True)
        return open(out, "rb").read()


class SmartPublishTests(PublishingBase):
    def recorder(self, calls, tiktok_creator=None, comment_fails=False):
        creator = tiktok_creator or {"privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"], "creator_nickname": "My Shop",
                                     "max_video_post_duration_sec": 600, "duet_disabled": False}

        def http(method, url, **kw):
            calls.append((method, url.split("?")[0], kw))
            u = url
            if u.endswith("/comments"):
                if comment_fails:
                    from publishing.platforms.base import PublishError
                    raise PublishError("(#10) permission")
                return FakeResp(), {"id": "C1"}
            if u.endswith("/PAGE1/videos"):
                return FakeResp(), {"id": "VID1"}
            if u.endswith("/IG1/media"):
                return FakeResp(), {"id": "CONTAINER1"}
            if u.endswith("/CONTAINER1"):
                return FakeResp(), {"status_code": "FINISHED"}
            if u.endswith("/IG1/media_publish"):
                return FakeResp(), {"id": "IGMEDIA1"}
            if u.endswith("/IGMEDIA1"):
                return FakeResp(), {"permalink": "https://instagram.com/reel/abc"}
            if "upload/youtube" in u:
                return FakeResp({"Location": "https://upload.example/session1"}), {}
            if u == "https://upload.example/session1":
                return FakeResp(), {"id": "YT123"}
            if u.endswith("/creator_info/query/"):
                return FakeResp(), {"data": creator, "error": {"code": "ok"}}
            if u.endswith("/video/init/"):
                return FakeResp(), {"data": {"publish_id": "PUB1", "upload_url": "https://tt-upload.example/1"}, "error": {"code": "ok"}}
            if u.endswith("/status/fetch/"):
                return FakeResp(), {"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}}
            if u == "https://tt-upload.example/1":
                return FakeResp(), {}
            raise AssertionError(f"unexpected call {method} {u}")
        return mock.patch.object(Publisher, "http", staticmethod(http))

    def video(self, seconds=4, size="320x568"):
        data = make_video(seconds, size)
        if data is None:
            self.skipTest("ffmpeg not installed")
        res = self.c.post("/api/publishing/media/", {"file": SimpleUploadedFile("clip.mp4", data)}, format="multipart")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def test_upload_reads_video_size_and_length(self):
        v = self.video(4, "320x568")
        self.assertEqual((v["width"], v["height"]), (320, 568))
        self.assertAlmostEqual(v["duration"], 4, delta=0.5)

    def test_every_platform_gets_its_own_settings(self):
        self.connect_meta()
        yt, tt = self.add_video_accounts()
        fb, ig = SocialAccount.objects.get(platform="facebook"), SocialAccount.objects.get(platform="instagram")
        vid = self.video()["id"]
        calls = []
        targets = [
            {"account_id": str(yt.id), "caption": "Full description", "options": {
                "title": "Dashain kurtas", "privacy": "unlisted", "tags": ["kurta", "#dashain", "kurta", "nepal fashion"],
                "category_id": "26", "made_for_kids": False, "notify_subscribers": False, "evil": "x"}},
            {"account_id": str(tt.id), "options": {"privacy": "PUBLIC_TO_EVERYONE", "disable_duet": True, "brand_organic": True}},
            {"account_id": str(ig.id), "options": {"share_to_feed": False, "collaborators": "@sita, ram", "first_comment": "#kurta"}},
            {"account_id": str(fb.id), "options": {"title": "New kurtas", "first_comment": "Order: 98xxxxxxxx"}},
        ]
        res = self.c.post("/api/publishing/posts/", {"caption": "New Dashain collection", "media_id": vid, "action": "publish",
                                                     "targets": targets}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        yt_opts = next(t for t in res.data["targets"] if t["account"]["platform"] == "youtube")["options"]
        self.assertEqual(yt_opts["tags"], ["kurta", "dashain", "nepal fashion"])  # cleaned, de-duplicated
        self.assertNotIn("evil", yt_opts)
        with self.recorder(calls):
            publish_post(res.data["id"])
        sent = {u: kw for _, u, kw in calls}
        yt_meta = sent["https://www.googleapis.com/upload/youtube/v3/videos"]["json"]
        self.assertEqual(yt_meta["snippet"]["categoryId"], "26")
        self.assertEqual(yt_meta["snippet"]["tags"], ["kurta", "dashain", "nepal fashion"])
        self.assertEqual(yt_meta["status"], {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False})
        tt_info = sent["https://open.tiktokapis.com/v2/post/publish/video/init/"]["json"]["post_info"]
        self.assertEqual((tt_info["privacy_level"], tt_info["disable_duet"], tt_info["brand_organic_toggle"]),
                         ("PUBLIC_TO_EVERYONE", True, True))
        ig_body = sent["https://graph.facebook.com/v21.0/IG1/media"]["data"]
        self.assertEqual((ig_body["media_type"], ig_body["share_to_feed"]), ("REELS", "false"))
        self.assertEqual(json.loads(ig_body["collaborators"]), ["sita", "ram"])
        self.assertEqual(sent["https://graph.facebook.com/v21.0/PAGE1/videos"]["data"]["title"], "New kurtas")
        self.assertIn("https://graph.facebook.com/v21.0/IGMEDIA1/comments", sent)
        self.assertIn("https://graph.facebook.com/v21.0/VID1/comments", sent)
        post = self.c.get(f"/api/publishing/posts/{res.data['id']}/").data
        self.assertEqual(post["status"], "published")

    def test_failed_first_comment_does_not_fail_the_post(self):
        self.connect_meta()
        fb = SocialAccount.objects.get(platform="facebook")
        vid = self.video()["id"]
        res = self.c.post("/api/publishing/posts/", {"caption": "x", "media_id": vid, "action": "publish",
                                                     "targets": [{"account_id": str(fb.id), "options": {"first_comment": "hi"}}]},
                          format="json")
        with self.recorder([], comment_fails=True):
            publish_post(res.data["id"])
        post = self.c.get(f"/api/publishing/posts/{res.data['id']}/").data
        self.assertEqual(post["status"], "published")
        self.assertIn("first comment", post["targets"][0]["options"]["note"])

    def test_checks(self):
        asset = MediaAsset(kind="video", mime="video/mp4", size=10, duration=1200, width=1920, height=1080)
        errs = validate_target("instagram", "x", asset, clean_options("instagram", {}))
        self.assertTrue(any("at most 15 minutes" in e for e in errs))
        errs = validate_target("tiktok", "x", asset, clean_options("tiktok", {"privacy": "SELF_ONLY", "brand_content": True}))
        self.assertTrue(any("Branded content" in e for e in errs))
        self.assertTrue(any("TikTok videos can be at most" in e for e in errs))
        errs = validate_target("tiktok", "x", asset, clean_options("tiktok", {}))
        self.assertIn("Choose who can see the TikTok video.", errs)
        errs = validate_target("youtube", "x", asset, clean_options("youtube", {"title": "a <b>", "tags": [f"tag{i}" + "t" * 90 for i in range(8)]}))
        self.assertTrue(any("< or >" in e for e in errs))
        self.assertTrue(any("500 characters" in e for e in errs))

    def test_tiktok_privacy_not_allowed_by_creator_fails_clearly(self):
        _, tt = self.add_video_accounts()
        vid = self.video()["id"]
        res = self.c.post("/api/publishing/posts/", {"caption": "x", "media_id": vid, "action": "publish",
                                                     "targets": [{"account_id": str(tt.id), "options": {"privacy": "PUBLIC_TO_EVERYONE"}}]},
                          format="json")
        with self.recorder([], tiktok_creator={"privacy_level_options": ["SELF_ONLY"]}):
            publish_post(res.data["id"])
        post = self.c.get(f"/api/publishing/posts/{res.data['id']}/").data
        self.assertEqual(post["status"], "failed")
        self.assertIn("doesn't allow", post["targets"][0]["error"])

    def test_tiktok_creator_info_endpoint(self):
        _, tt = self.add_video_accounts()
        with self.recorder([]):
            res = self.c.get(f"/api/publishing/accounts/{tt.id}/tiktok/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["nickname"], "My Shop")
        self.assertEqual(res.data["privacy_options"], ["PUBLIC_TO_EVERYONE", "SELF_ONLY"])
        self.assertEqual(res.data["max_seconds"], 600)


    @override_settings(OPENROUTER_API_KEY="test-key")
    def test_ai_fills_every_platform_from_the_video(self):
        from automations.models import KnowledgeItem
        KnowledgeItem.objects.create(workspace=self.ws, title="Cotton kurta", content="Cotton kurta Rs 1,800. Delivery all over Nepal.")
        vid = self.video(4, "320x568")["id"]
        answers = ["यो कुर्ता रु १८०० मा पाइन्छ", json.dumps({
            "youtube": {"title": "Cotton kurta <new>", "description": "Desc", "tags": ["#kurta", "nepal"], "category_id": "26"},
            "instagram": {"caption": "IG caption #kurta"}, "tiktok": {"caption": "TT #kurta"},
            "facebook": {"caption": "FB caption", "title": "Kurta"}, "summary": "A kurta on a hanger",
            "checks": ["Horizontal video"]})]
        calls = []

        def fake(messages, **kw):
            calls.append((messages, kw))
            return answers[len(calls) - 1], 100
        with mock.patch("automations.llm.chat", side_effect=fake):
            res = self.c.post("/api/ai/publish-fill/", {"media_id": vid, "platforms": ["youtube", "instagram", "tiktok", "facebook"],
                                                         "language": "mixed"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(calls[0][0][0]["content"][1]["type"], "input_audio")  # listened to the video
        user_parts = calls[1][0][1]["content"]
        self.assertGreaterEqual(sum(p["type"] == "image_url" for p in user_parts), 2)  # looked at frames
        self.assertIn("कुर्ता", user_parts[0]["text"])
        self.assertIn("Rs 1,800", calls[1][0][0]["content"])  # business facts in the prompt
        self.assertEqual(res.data["youtube"]["title"], "Cotton kurta new")
        self.assertEqual(res.data["youtube"]["tags"], ["kurta", "nepal"])
        self.assertEqual(res.data["instagram"]["caption"], "IG caption #kurta")
        self.assertEqual(res.data["credits_used"], 2)
        from automations.models import AIUsage
        self.assertEqual(AIUsage.objects.get().credits, 2)


__all__ = ["SmartPublishTests"]
