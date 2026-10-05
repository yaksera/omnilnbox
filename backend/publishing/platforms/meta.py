"""Facebook Page and Instagram (professional account) publishing via the Graph API."""
import json
import logging
import time

from ..media import public_url
from .base import PublishError, Publisher

GRAPH = "https://graph.facebook.com/v21.0"
logger = logging.getLogger(__name__)


def first_comment(target, object_id, token, text):
    """Post the first comment (hashtags, links...). A failure never fails the post: it's noted for the team."""
    if not text.strip():
        return
    try:
        graph("POST", f"{object_id}/comments", token, data={"message": text})
    except PublishError as exc:
        logger.info("First comment failed on %s: %s", object_id, exc)
        note = "Published, but the first comment couldn't be added (the account may need comment permission)."
        target.options = {**(target.options or {}), "note": note}


def graph(method, path, token, **kw):
    headers = kw.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    try:
        return Publisher.http(method, f"{GRAPH}/{path.lstrip('/')}", headers=headers, **kw)[1]
    except PublishError as exc:
        err = exc.detail.get("error") or {}
        if err.get("code") == 190:
            raise PublishError("The Meta access token expired or was revoked. Reconnect this account with a "
                               "System User token set to 'Never' expire.", detail=exc.detail) from exc
        raise


def discover_pages(token, page_id=None):
    """Return the Pages this token manages (with Page tokens) and any linked Instagram accounts."""
    data = graph("GET", "me/accounts", token, params={
        "fields": "id,name,access_token,picture{url},instagram_business_account{id,username,profile_picture_url}",
        "limit": "100",
    })
    pages = data.get("data", [])
    if page_id:
        pages = [p for p in pages if str(p.get("id")) == str(page_id)]
    return pages


class FacebookPublisher(Publisher):
    platform = "facebook"

    def publish(self, target, asset):
        token, page = self.creds["page_token"], self.account.external_id
        caption = target.caption or target.post.caption
        if asset is None:
            res = graph("POST", f"{page}/feed", token, data={"message": caption})
            post_id = res["id"]
        elif asset.kind == "image":
            res = graph("POST", f"{page}/photos", token, data={"url": public_url(asset), "caption": caption})
            post_id = res.get("post_id") or res["id"]
        else:
            data = {"file_url": public_url(asset), "description": caption}
            if (target.options or {}).get("title"):
                data["title"] = target.options["title"]
            res = graph("POST", f"{page}/videos", token, data=data)
            post_id = res["id"]
        first_comment(target, post_id, token, (target.options or {}).get("first_comment", ""))
        return post_id, f"https://www.facebook.com/{post_id}"


class InstagramPublisher(Publisher):
    platform = "instagram"
    POLL_SECONDS, POLL_TRIES = 5, 60  # videos can take a few minutes to process

    def publish(self, target, asset):
        token, ig = self.creds["page_token"], self.account.external_id
        caption = target.caption or target.post.caption
        opts = target.options or {}
        body = {"caption": caption}
        if asset.kind == "image":
            body["image_url"] = public_url(asset)
        else:
            body.update(media_type="REELS", video_url=public_url(asset),
                        share_to_feed="true" if opts.get("share_to_feed", True) else "false")
            if opts.get("cover_ms"):
                body["thumb_offset"] = str(int(opts["cover_ms"]))
        if opts.get("collaborators"):
            body["collaborators"] = json.dumps(list(opts["collaborators"])[:3])
        container = graph("POST", f"{ig}/media", token, data=body)["id"]
        for _ in range(self.POLL_TRIES):  # wait until Instagram has fetched and processed the media
            status = graph("GET", container, token, params={"fields": "status_code,status"}).get("status_code")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise PublishError(f"Instagram could not process the media ({status}). Check the format "
                                   "(JPEG image, or MP4/H.264 video) and that your server is publicly reachable.")
            time.sleep(self.POLL_SECONDS)
        else:
            raise PublishError("Instagram took too long to process the video.")
        media_id = graph("POST", f"{ig}/media_publish", token, data={"creation_id": container})["id"]
        link = graph("GET", media_id, token, params={"fields": "permalink"}).get("permalink", "")
        first_comment(target, media_id, token, opts.get("first_comment", ""))
        return media_id, link
