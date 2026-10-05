from urllib.parse import urlparse

import requests

from integrations.providers.base import ProviderError

LIMITS = {
    # caption / title limits and media rules the composer validates before publishing
    "facebook": {"caption": 63206, "needs_media": False, "video_only": False, "jpeg_only": False},
    "instagram": {"caption": 2200, "needs_media": True, "video_only": False, "jpeg_only": True},
    "youtube": {"caption": 5000, "title": 100, "needs_media": True, "video_only": True, "jpeg_only": False},
    "tiktok": {"caption": 2200, "needs_media": True, "video_only": True, "jpeg_only": False},
}


# YouTube categories a video can be uploaded to (videoCategories, same in every region we target)
YT_CATEGORIES = {
    "1": "Film & Animation", "2": "Autos & Vehicles", "10": "Music", "15": "Pets & Animals", "17": "Sports",
    "19": "Travel & Events", "20": "Gaming", "22": "People & Blogs", "23": "Comedy", "24": "Entertainment",
    "25": "News & Politics", "26": "Howto & Style", "27": "Education", "28": "Science & Technology",
    "29": "Nonprofits & Activism",
}
TIKTOK_PRIVACY = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]
# Video length each platform accepts (seconds). TikTok's real maximum comes from the creator (creator_info).
NAMES = {"facebook": "Facebook", "instagram": "Instagram", "youtube": "YouTube", "tiktok": "TikTok"}
DURATION = {"instagram": (3, 900), "tiktok": (3, 600), "youtube": (1, 12 * 3600), "facebook": (1, 4 * 3600)}


def _bool(v):
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def _words(v, limit, each=100):
    items = v if isinstance(v, list) else str(v or "").split(",")
    out = []
    for x in items:
        x = " ".join(str(x).replace("#", " ").split()).strip()[:each]
        if x and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out[:limit]


def clean_options(platform, raw):
    """Keep only the settings each platform supports, in the right types."""
    raw = raw if isinstance(raw, dict) else {}
    o = {}
    if platform == "youtube":
        o["title"] = str(raw.get("title") or "")[:100]
        o["privacy"] = raw.get("privacy") if raw.get("privacy") in ("public", "unlisted", "private") else "public"
        o["tags"] = _words(raw.get("tags"), 40)
        o["category_id"] = str(raw.get("category_id")) if str(raw.get("category_id")) in YT_CATEGORIES else "22"
        o["made_for_kids"] = _bool(raw.get("made_for_kids", False))
        o["notify_subscribers"] = _bool(raw.get("notify_subscribers", True))
    elif platform == "tiktok":
        o["privacy"] = raw.get("privacy") if raw.get("privacy") in TIKTOK_PRIVACY else ""
        for k in ("disable_comment", "disable_duet", "disable_stitch", "brand_organic", "brand_content"):
            o[k] = _bool(raw.get(k, False))
        try:
            o["cover_ms"] = max(0, int(raw.get("cover_ms") or 0))
        except (TypeError, ValueError):
            o["cover_ms"] = 0
    elif platform == "instagram":
        o["share_to_feed"] = _bool(raw.get("share_to_feed", True))
        o["collaborators"] = [c.lstrip("@") for c in _words(raw.get("collaborators"), 3, 30)]
        o["first_comment"] = str(raw.get("first_comment") or "")[:2200]
        try:
            o["cover_ms"] = max(0, int(raw.get("cover_ms") or 0))
        except (TypeError, ValueError):
            o["cover_ms"] = 0
    elif platform == "facebook":
        o["title"] = str(raw.get("title") or "")[:255]
        o["first_comment"] = str(raw.get("first_comment") or "")[:8000]
    return o


class PublishError(ProviderError):
    pass


class Publisher:
    platform = ""

    def __init__(self, account):
        self.account = account
        self.creds = account.credentials or {}

    def save_creds(self):
        self.account.credentials = self.creds
        self.account.save(update_fields=["credentials"])

    @staticmethod
    def http(method, url, **kw):
        kw.setdefault("timeout", 60)
        try:
            resp = requests.request(method, url, **kw)
        except requests.Timeout as exc:
            raise PublishError(f"{urlparse(url).netloc} took too long to respond. Try again.") from exc
        except requests.RequestException as exc:
            raise PublishError(f"Couldn't reach {urlparse(url).netloc}. Check the server's internet connection.") from exc
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {"raw": resp.text[:300]}
        if resp.status_code >= 400:
            raise PublishError(f"{resp.status_code} from {url.split('?')[0]}: {body}", status=resp.status_code,
                               detail=body if isinstance(body, dict) else {})
        return resp, body

    def publish(self, target, asset):
        """Publish and return (external_id, url)."""
        raise NotImplementedError


def validate_target(platform, caption, asset, options):
    """Return a list of human-readable problems (empty = OK)."""
    rules, errors = LIMITS[platform], []
    if len(caption) > rules["caption"]:
        errors.append(f"Caption is too long for {platform} ({len(caption)}/{rules['caption']}).")
    if rules["needs_media"] and asset is None:
        errors.append(f"{platform.title()} needs {'a video' if rules['video_only'] else 'an image or video'}.")
    if asset is not None:
        if rules["video_only"] and asset.kind != "video":
            errors.append(f"{platform.title()} only accepts videos.")
        if rules["jpeg_only"] and asset.kind == "image" and asset.mime != "image/jpeg":
            errors.append("Instagram only accepts JPEG images.")
    if asset is not None and asset.kind == "video" and asset.duration and platform in DURATION:
        low, high = DURATION[platform]
        if asset.duration < low:
            errors.append(f"{NAMES[platform]} videos must be at least {low} seconds long.")
        elif asset.duration > high:
            errors.append(f"{NAMES[platform]} videos can be at most {high // 60} minutes long.")
    if platform == "youtube":
        title = (options.get("title") or "").strip()
        if not title:
            errors.append("YouTube needs a video title.")
        elif len(title) > 100:
            errors.append("YouTube titles can be at most 100 characters.")
        if len(",".join(options.get("tags") or [])) > 500:
            errors.append("YouTube tags can be at most 500 characters in total.")
        if "<" in title or ">" in title:
            errors.append("YouTube titles can't contain < or >.")
    if platform == "tiktok":
        if not options.get("privacy"):
            errors.append("Choose who can see the TikTok video.")
        if options.get("brand_content") and options.get("privacy") == "SELF_ONLY":
            errors.append("Branded content on TikTok can't be private.")
    if platform == "facebook" and not caption.strip() and asset is None:
        errors.append("Facebook needs text or media.")
    return errors
