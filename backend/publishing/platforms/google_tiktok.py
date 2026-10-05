"""YouTube (Google OAuth + resumable upload) and TikTok (Login Kit + Content Posting API)."""
import math
import time
from urllib.parse import urlencode

from django.conf import settings

from .base import PublishError, Publisher


def oauth_redirect(platform):
    return f"{settings.PUBLIC_BASE_URL}/api/publishing/oauth/{platform}/callback/"


# ----------------------------------------------------------------------------------------- YouTube
class YouTube:
    AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN = "https://oauth2.googleapis.com/token"
    SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"

    @staticmethod
    def enabled():
        return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)

    @classmethod
    def authorize_url(cls, state):
        return f"{cls.AUTH}?" + urlencode({
            "client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": oauth_redirect("youtube"),
            "response_type": "code", "scope": cls.SCOPES, "access_type": "offline",
            "prompt": "consent", "include_granted_scopes": "true", "state": state,
        })

    @classmethod
    def exchange(cls, code):
        _, tok = Publisher.http("POST", cls.TOKEN, data={
            "code": code, "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": oauth_redirect("youtube"), "grant_type": "authorization_code",
        })
        _, ch = Publisher.http("GET", "https://www.googleapis.com/youtube/v3/channels",
                               params={"part": "snippet", "mine": "true"},
                               headers={"Authorization": f"Bearer {tok['access_token']}"})
        items = ch.get("items") or []
        if not items:
            raise PublishError("This Google account has no YouTube channel.")
        sn = items[0]["snippet"]
        return {
            "external_id": items[0]["id"], "name": sn.get("title", "YouTube channel"),
            "avatar_url": (sn.get("thumbnails", {}).get("default") or {}).get("url", ""),
            "credentials": {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", ""),
                            "expires_at": int(time.time()) + int(tok.get("expires_in", 3600)) - 60},
        }


class YouTubePublisher(Publisher):
    platform = "youtube"

    def token(self):
        if self.creds.get("access_token") and int(self.creds.get("expires_at", 0)) > time.time():
            return self.creds["access_token"]
        if not self.creds.get("refresh_token"):
            raise PublishError("YouTube access expired. Reconnect the channel.")
        _, tok = self.http("POST", YouTube.TOKEN, data={
            "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": self.creds["refresh_token"], "grant_type": "refresh_token",
        })
        self.creds["access_token"] = tok["access_token"]
        self.creds["expires_at"] = int(time.time()) + int(tok.get("expires_in", 3600)) - 60
        self.save_creds()
        return self.creds["access_token"]

    def publish(self, target, asset):
        opts = target.options or {}
        headers = {"Authorization": f"Bearer {self.token()}", "X-Upload-Content-Type": asset.mime,
                   "X-Upload-Content-Length": str(asset.size)}
        meta = {
            "snippet": {"title": opts.get("title", "")[:100], "description": (target.caption or target.post.caption)[:5000],
                        "categoryId": str(opts.get("category_id") or "22"), "tags": list(opts.get("tags") or [])[:40]},
            "status": {"privacyStatus": opts.get("privacy", "public"),
                       "selfDeclaredMadeForKids": bool(opts.get("made_for_kids", False))},
        }
        resp, _ = self.http("POST", "https://www.googleapis.com/upload/youtube/v3/videos",
                            params={"uploadType": "resumable", "part": "snippet,status",
                                    "notifySubscribers": "true" if opts.get("notify_subscribers", True) else "false"},
                            headers=headers, json=meta)
        upload_url = resp.headers.get("Location")
        if not upload_url:
            raise PublishError("YouTube did not return an upload URL.")
        with asset.file.open("rb") as fh:
            _, video = self.http("PUT", upload_url, data=fh, timeout=3600,
                                 headers={"Content-Type": asset.mime, "Content-Length": str(asset.size)})
        return video["id"], f"https://youtu.be/{video['id']}"


# ----------------------------------------------------------------------------------------- TikTok
class TikTok:
    AUTH = "https://www.tiktok.com/v2/auth/authorize/"
    API = "https://open.tiktokapis.com/v2"
    SCOPES = "user.info.basic,video.publish"

    @staticmethod
    def enabled():
        return bool(settings.TIKTOK_CLIENT_KEY and settings.TIKTOK_CLIENT_SECRET)

    @classmethod
    def authorize_url(cls, state):
        return f"{cls.AUTH}?" + urlencode({
            "client_key": settings.TIKTOK_CLIENT_KEY, "scope": cls.SCOPES, "response_type": "code",
            "redirect_uri": oauth_redirect("tiktok"), "state": state,
        })

    @classmethod
    def _token(cls, **data):
        _, tok = Publisher.http("POST", f"{cls.API}/oauth/token/", data={
            "client_key": settings.TIKTOK_CLIENT_KEY, "client_secret": settings.TIKTOK_CLIENT_SECRET, **data},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        if "access_token" not in tok:
            raise PublishError(f"TikTok token error: {tok.get('error_description') or tok}")
        return tok

    @classmethod
    def exchange(cls, code):
        tok = cls._token(code=code, grant_type="authorization_code", redirect_uri=oauth_redirect("tiktok"))
        _, info = Publisher.http("GET", f"{cls.API}/user/info/", params={"fields": "open_id,display_name,avatar_url"},
                                 headers={"Authorization": f"Bearer {tok['access_token']}"})
        user = (info.get("data") or {}).get("user") or {}
        return {
            "external_id": tok["open_id"], "name": user.get("display_name") or "TikTok account",
            "avatar_url": user.get("avatar_url", ""),
            "credentials": {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", ""),
                            "expires_at": int(time.time()) + int(tok.get("expires_in", 86400)) - 60},
        }


class TikTokPublisher(Publisher):
    platform = "tiktok"
    MIN_CHUNK, MAX_CHUNK = 5 * 1024 * 1024, 64 * 1024 * 1024

    def token(self):
        if self.creds.get("access_token") and int(self.creds.get("expires_at", 0)) > time.time():
            return self.creds["access_token"]
        tok = TikTok._token(grant_type="refresh_token", refresh_token=self.creds.get("refresh_token", ""))
        self.creds.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token", self.creds.get("refresh_token")),
                          expires_at=int(time.time()) + int(tok.get("expires_in", 86400)) - 60)
        self.save_creds()
        return self.creds["access_token"]

    def _api(self, path, body):
        _, data = self.http("POST", f"{TikTok.API}{path}", json=body,
                            headers={"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json; charset=UTF-8"})
        err = data.get("error") or {}
        if err.get("code") not in (None, "ok"):
            raise PublishError(f"TikTok: {err.get('message') or err.get('code')}")
        return data.get("data") or {}

    CHUNK = 50 * 1024 * 1024

    @classmethod
    def plan_chunks(cls, size):
        """TikTok rules: a video up to 64 MB can be sent whole (and must be, under 5 MB).
        Bigger videos go in 5-64 MB chunks; the last chunk absorbs the remainder (max 128 MB)."""
        if size <= cls.MAX_CHUNK:
            return size, 1
        return cls.CHUNK, math.floor(size / cls.CHUNK)

    def creator_info(self):
        return self._api("/post/publish/creator_info/query/", {})

    def publish(self, target, asset):
        opts = target.options or {}
        creator = self.creator_info()
        allowed = creator.get("privacy_level_options") or ["SELF_ONLY"]
        if opts.get("privacy") and opts["privacy"] not in allowed:
            raise PublishError(f"TikTok doesn't allow \"{opts['privacy']}\" for this account right now. Choose another privacy option.")
        privacy = opts.get("privacy") or ("SELF_ONLY" if "SELF_ONLY" in allowed else allowed[0])
        max_s = int(creator.get("max_video_post_duration_sec") or 0)
        if max_s and asset.duration and asset.duration > max_s:
            raise PublishError(f"This TikTok account can post videos up to {max_s // 60} min {max_s % 60} s.")
        post_info = {
            "title": (target.caption or target.post.caption)[:2200], "privacy_level": privacy,
            "disable_comment": bool(opts.get("disable_comment") or creator.get("comment_disabled")),
            "disable_duet": bool(opts.get("disable_duet") or creator.get("duet_disabled")),
            "disable_stitch": bool(opts.get("disable_stitch") or creator.get("stitch_disabled")),
            "brand_organic_toggle": bool(opts.get("brand_organic")),
            "brand_content_toggle": bool(opts.get("brand_content")),
        }
        if opts.get("cover_ms"):
            post_info["video_cover_timestamp_ms"] = int(opts["cover_ms"])
        chunk, count = self.plan_chunks(asset.size)
        init = self._api("/post/publish/video/init/", {
            "post_info": post_info,
            "source_info": {"source": "FILE_UPLOAD", "video_size": asset.size, "chunk_size": chunk, "total_chunk_count": count},
        })
        publish_id, upload_url = init["publish_id"], init["upload_url"]
        with asset.file.open("rb") as fh:
            for i in range(count):
                start = i * chunk
                end = asset.size - 1 if i == count - 1 else start + chunk - 1
                fh.seek(start)
                part = fh.read(end - start + 1)
                self.http("PUT", upload_url, data=part, timeout=600, headers={
                    "Content-Type": asset.mime, "Content-Length": str(len(part)),
                    "Content-Range": f"bytes {start}-{end}/{asset.size}"})
        for _ in range(60):  # wait for TikTok to process
            st = self._api("/post/publish/status/fetch/", {"publish_id": publish_id})
            if st.get("status") == "PUBLISH_COMPLETE":
                break
            if st.get("status") == "FAILED":
                raise PublishError(f"TikTok rejected the video: {st.get('fail_reason', 'unknown reason')}")
            time.sleep(5)
        note = "" if privacy == "PUBLIC_TO_EVERYONE" else f" (posted as {privacy}; public posting needs TikTok's audit)"
        target.options = {**opts, "note": note.strip()}
        return publish_id, ""

