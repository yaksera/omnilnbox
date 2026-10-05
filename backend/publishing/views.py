import mimetypes
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.plans import F_PUBLISH, F_SCHEDULE
from core.permissions import require, require_feature
from core.tenancy import get_membership
from integrations.meta_connect import long_lived, publish_login_config, token_info
from integrations.providers.base import ProviderError

from . import media as media_utils
from .models import MediaAsset, Post, PostTarget, SocialAccount
from .platforms.base import LIMITS, YT_CATEGORIES, PublishError, clean_options, validate_target
from .platforms.google_tiktok import TikTok, YouTube
from .platforms.meta import discover_pages

PUBLISH_SCOPES = {"pages_show_list", "pages_manage_posts"}
from .services import publish_in_background, retry_failed

OAUTH_SALT = "omniinbox.publishing.oauth"
PLATFORM_LABELS = {"facebook": "Facebook Page", "instagram": "Instagram", "youtube": "YouTube", "tiktok": "TikTok"}


def _account_json(a):
    return {"id": str(a.id), "platform": a.platform, "name": a.name, "avatar_url": a.avatar_url,
            "status": a.status, "last_error": a.last_error, "created_at": a.created_at}


def _asset_json(asset):
    if asset is None:
        return None
    return {"id": str(asset.id), "kind": asset.kind, "mime": asset.mime, "size": asset.size,
            "name": asset.original_name, "preview_url": media_utils.preview_path(asset),
            "width": asset.width, "height": asset.height, "duration": asset.duration}


def _post_json(p):
    return {
        "id": str(p.id), "caption": p.caption, "status": p.status, "scheduled_at": p.scheduled_at,
        "published_at": p.published_at, "created_at": p.created_at, "media": _asset_json(p.media),
        "created_by": (p.created_by.get_full_name() or p.created_by.email) if p.created_by else "",
        "targets": [{
            "account": _account_json(t.account), "caption": t.caption, "options": t.options, "status": t.status,
            "url": t.url, "error": t.error, "published_at": t.published_at,
        } for t in p.targets.all()],
    }


# ------------------------------------------------------------------ config + accounts
class ConfigView(APIView):
    def get(self, request):
        ws = get_membership(request).workspace
        return Response({
            "platforms": {
                "facebook": {"label": "Facebook Page", "connect": "token", "enabled": True},
                "instagram": {"label": "Instagram", "connect": "via_facebook", "enabled": True},
                "youtube": {"label": "YouTube", "connect": "oauth", "enabled": YouTube.enabled()},
                "tiktok": {"label": "TikTok", "connect": "oauth", "enabled": TikTok.enabled()},
            },
            "limits": LIMITS,
            "youtube_categories": YT_CATEGORIES,
            "features": {"publish": ws.has_feature(F_PUBLISH), "schedule": ws.has_feature(F_SCHEDULE)},
            "account_limit": ws.channel_limit,
            "facebook_login": publish_login_config(),  # one-click "Continue with Facebook" (None = token only)
        })


class AccountsView(APIView):
    def get(self, request):
        ws = get_membership(request).workspace
        return Response([_account_json(a) for a in SocialAccount.objects.filter(workspace=ws)])


def _check_account_limit(ws, adding=1):
    if SocialAccount.objects.filter(workspace=ws).count() + adding > ws.channel_limit:
        raise serializers.ValidationError({"detail": f"Your {ws.plan_info['name']} plan allows "
                                                     f"{ws.channel_limit} publishing accounts. Upgrade to add more."})


class ConnectFacebookView(APIView):
    """POST {access_token, page_id?}: connects the Facebook Page and its linked Instagram account."""

    def post(self, request):
        m = require(request, "manage_social_accounts")
        require_feature(m.workspace, F_PUBLISH)
        token = str(request.data.get("access_token", "")).strip()
        if not token:
            return Response({"access_token": ["Paste a (never-expiring) System User token."]}, status=400)
        if request.data.get("via") == "facebook_login":
            # Token from the "Continue with Facebook" popup: check it's ours and allows posting, then make it permanent
            try:
                info = token_info(token)
                missing = PUBLISH_SCOPES - set(info.get("scopes") or [])
                if missing:
                    return Response({"detail": "Facebook didn't grant posting permission (" + ", ".join(sorted(missing)) +
                                               "). Add pages_show_list, pages_manage_posts, pages_read_engagement, "
                                               "instagram_basic and instagram_content_publish to the Facebook Login "
                                               "configuration used for publishing, then try again."}, status=400)
                token = long_lived(token)
            except ProviderError as exc:
                return Response({"detail": str(exc)[:400]}, status=400)
        try:
            pages = discover_pages(token, request.data.get("page_id") or None)
        except PublishError as exc:
            return Response({"detail": str(exc)[:400]}, status=400)
        if not pages:
            return Response({"detail": "No Facebook Pages found for this token (check the Page ID and that the "
                                       "token has pages_show_list and pages_manage_posts)."}, status=400)
        created = []
        with transaction.atomic():
            for pg in pages:
                items = [("facebook", pg["id"], pg["name"], (pg.get("picture") or {}).get("data", {}).get("url", ""))]
                ig = pg.get("instagram_business_account")
                if ig:
                    items.append(("instagram", ig["id"], f"@{ig.get('username', ig['id'])}", ig.get("profile_picture_url", "")))
                for platform, ext, name, avatar in items:
                    acc = SocialAccount.objects.filter(workspace=m.workspace, platform=platform, external_id=ext).first()
                    if acc is None:
                        _check_account_limit(m.workspace)
                        acc = SocialAccount(workspace=m.workspace, platform=platform, external_id=ext, created_by=request.user)
                    acc.name, acc.avatar_url, acc.status, acc.last_error = name, avatar[:1000], "active", ""
                    acc.credentials = {"page_token": pg["access_token"], "page_id": pg["id"]}
                    acc.save()
                    created.append(_account_json(acc))
        from accounts.audit import audit
        audit(request, "social.connected", target=", ".join(a["name"] for a in created))
        return Response({"accounts": created}, status=201)


class AccountDetailView(APIView):
    def delete(self, request, account_id):
        m = require(request, "manage_social_accounts")
        from accounts.audit import audit
        for acc in SocialAccount.objects.filter(workspace=m.workspace, id=account_id):
            audit(request, "social.removed", target=f"{acc.get_platform_display()}: {acc.name}")
            acc.delete()
        return Response(status=204)


class OAuthStartView(APIView):
    def post(self, request, platform):
        m = require(request, "manage_social_accounts")
        require_feature(m.workspace, F_PUBLISH)
        provider = {"youtube": YouTube, "tiktok": TikTok}.get(platform)
        if provider is None or not provider.enabled():
            return Response({"detail": f"{platform.title()} isn't configured on this server yet "
                                       f"(add its API keys to backend/.env)."}, status=400)
        _check_account_limit(m.workspace)
        state = signing.dumps({"w": str(m.workspace_id), "u": request.user.id, "p": platform}, salt=OAUTH_SALT)
        return Response({"url": provider.authorize_url(state)})


def _back(status_, message=""):
    q = {"connected": status_}
    if message:
        q["message"] = message[:160]
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/publish/accounts?{urlencode(q)}")


def oauth_callback(request, platform):
    try:
        state = signing.loads(request.GET.get("state", ""), salt=OAUTH_SALT, max_age=900)
    except signing.BadSignature:
        return _back("error", "The sign-in link expired. Please try again.")
    if state.get("p") != platform or request.GET.get("error"):
        return _back("error", request.GET.get("error_description") or request.GET.get("error") or "Sign-in was cancelled.")
    provider = {"youtube": YouTube, "tiktok": TikTok}[platform]
    try:
        info = provider.exchange(request.GET.get("code", ""))
    except PublishError as exc:
        return _back("error", str(exc))
    SocialAccount.objects.update_or_create(
        workspace_id=state["w"], platform=platform, external_id=info["external_id"],
        defaults={"name": info["name"], "avatar_url": info["avatar_url"][:1000], "credentials": info["credentials"],
                  "status": "active", "last_error": "", "created_by_id": state["u"]},
    )
    return _back(platform)


# ------------------------------------------------------------------ media
class MediaUploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        m = get_membership(request)
        require_feature(m.workspace, F_PUBLISH)
        f = request.FILES.get("file")
        if f is None:
            return Response({"file": ["Choose a file."]}, status=400)
        head = f.read(16)
        f.seek(0)
        mime = media_utils.sniff(head)
        if mime in media_utils.IMAGE_TYPES:
            kind, limit = "image", media_utils.MAX_IMAGE
        elif mime in media_utils.VIDEO_TYPES:
            kind, limit = "video", media_utils.MAX_VIDEO
        else:
            return Response({"file": ["Upload a JPEG or PNG image, or an MP4/MOV video."]}, status=400)
        if f.size > limit:
            return Response({"file": [f"File too large (max {limit // (1024 * 1024)} MB for {kind}s)."]}, status=400)
        asset = MediaAsset(workspace=m.workspace, kind=kind, mime=mime, size=f.size,
                           original_name=f.name[:255], uploaded_by=request.user)
        asset.file.save(f"upload.{media_utils.IMAGE_TYPES.get(mime) or media_utils.VIDEO_TYPES[mime]}", f, save=False)
        asset.save()
        info = media_utils.probe(asset)  # size and length, for the per-platform checks
        if info:
            asset.width, asset.height, asset.duration = info.get("width"), info.get("height"), info.get("duration")
            asset.save(update_fields=["width", "height", "duration"])
        return Response(_asset_json(asset), status=201)


def media_file(request, token):
    """Serve a media file for a signed token (public links: 24 h, previews: 1 h)."""
    try:
        data = signing.loads(token, salt=media_utils.SALT, max_age=24 * 3600)
        if data.get("p") == "preview":
            signing.loads(token, salt=media_utils.SALT, max_age=3600)
    except signing.BadSignature:
        raise Http404
    asset = MediaAsset.objects.filter(id=data["a"]).first()
    if asset is None:
        raise Http404
    resp = FileResponse(asset.file.open("rb"), content_type=asset.mime or mimetypes.guess_type(asset.file.name)[0])
    resp["Cache-Control"] = "private, max-age=3600"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


# ------------------------------------------------------------------ posts
class TargetIn(serializers.Serializer):
    account_id = serializers.UUIDField()
    caption = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
    options = serializers.DictField(required=False, default=dict)


class PostIn(serializers.Serializer):
    caption = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
    media_id = serializers.UUIDField(required=False, allow_null=True)
    targets = TargetIn(many=True)
    action = serializers.ChoiceField(choices=["draft", "publish", "schedule"], default="draft")
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_targets(self, value):
        if not value:
            raise serializers.ValidationError("Choose at least one account.")
        return value


def _save_post(request, post, data):
    m = get_membership(request)
    ws = m.workspace
    require_feature(ws, F_PUBLISH)
    action = data["action"]
    if action in ("publish", "schedule"):
        require(request, "publish_posts")
    if action == "schedule":
        require_feature(ws, F_SCHEDULE)
        when = data.get("scheduled_at")
        if not when or when <= timezone.now() + timedelta(seconds=30):
            raise serializers.ValidationError({"scheduled_at": ["Pick a time in the future."]})
    asset = None
    if data.get("media_id"):
        asset = MediaAsset.objects.filter(workspace=ws, id=data["media_id"]).first()
        if asset is None:
            raise serializers.ValidationError({"media_id": ["Unknown media."]})
    accounts = {str(a.id): a for a in SocialAccount.objects.filter(workspace=ws, id__in=[t["account_id"] for t in data["targets"]])}
    problems = {}
    for t in data["targets"]:
        acc = accounts.get(str(t["account_id"]))
        if acc is None:
            raise serializers.ValidationError({"targets": ["Unknown account."]})
        t["options"] = clean_options(acc.platform, t["options"])
        if action != "draft":
            errs = validate_target(acc.platform, t["caption"] or data["caption"], asset, t["options"])
            if errs:
                problems[f"{PLATFORM_LABELS[acc.platform]} · {acc.name}"] = errs
    if problems:
        raise serializers.ValidationError({"targets": [f"{k}: {' '.join(v)}" for k, v in problems.items()]})

    with transaction.atomic():
        post.workspace, post.caption, post.media = ws, data["caption"], asset
        post.created_by = post.created_by or request.user
        post.status = {"draft": "draft", "publish": "scheduled", "schedule": "scheduled"}[action]
        post.scheduled_at = timezone.now() if action == "publish" else data.get("scheduled_at") if action == "schedule" else None
        post.save()
        post.targets.all().delete()
        for t in data["targets"]:
            PostTarget.objects.create(post=post, account=accounts[str(t["account_id"])], caption=t["caption"],
                                      options=t["options"])
    if action == "publish":
        transaction.on_commit(lambda: publish_in_background(post.id))
    return post


class PostsView(APIView):
    def get(self, request):
        ws = get_membership(request).workspace
        qs = Post.objects.filter(workspace=ws).select_related("media", "created_by").prefetch_related("targets__account")
        start, end = parse_datetime(request.query_params.get("from") or ""), parse_datetime(request.query_params.get("to") or "")
        if start and end:  # calendar range: scheduled or published in the window
            from django.db.models import Q
            qs = qs.filter(Q(scheduled_at__range=(start, end)) | Q(published_at__range=(start, end)))
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response([_post_json(p) for p in qs[:200]])

    def post(self, request):
        ser = PostIn(data=request.data)
        ser.is_valid(raise_exception=True)
        post = _save_post(request, Post(), ser.validated_data)
        post.refresh_from_db()
        return Response(_post_json(post), status=status.HTTP_201_CREATED)


class PostDetailView(APIView):
    def _get(self, request, post_id):
        return get_object_or_404(Post, id=post_id, workspace=get_membership(request).workspace)

    def get(self, request, post_id):
        return Response(_post_json(self._get(request, post_id)))

    def put(self, request, post_id):
        post = self._get(request, post_id)
        if post.status not in ("draft", "scheduled", "failed"):
            return Response({"detail": "Published posts can't be edited here."}, status=400)
        if post.status == "scheduled":
            require(request, "publish_posts")
        ser = PostIn(data=request.data)
        ser.is_valid(raise_exception=True)
        post = _save_post(request, post, ser.validated_data)
        post.refresh_from_db()
        return Response(_post_json(post))

    def delete(self, request, post_id):
        post = self._get(request, post_id)
        if post.status == "publishing":
            return Response({"detail": "This post is being published right now."}, status=400)
        if post.status != "draft":
            require(request, "publish_posts")
        post.delete()
        return Response(status=204)


class TikTokCreatorView(APIView):
    """GET accounts/<id>/tiktok/: what this TikTok creator may post (privacy options, max length, disabled interactions).
    TikTok requires apps to show these before posting."""

    def get(self, request, account_id):
        ws = get_membership(request).workspace
        acc = get_object_or_404(SocialAccount, workspace=ws, id=account_id, platform="tiktok")
        from .platforms.google_tiktok import TikTokPublisher
        try:
            info = TikTokPublisher(acc).creator_info()
        except PublishError as exc:
            return Response({"detail": str(exc)[:300]}, status=502)
        return Response({
            "nickname": info.get("creator_nickname") or acc.name, "username": info.get("creator_username", ""),
            "avatar_url": info.get("creator_avatar_url", ""),
            "privacy_options": info.get("privacy_level_options") or ["SELF_ONLY"],
            "comment_disabled": bool(info.get("comment_disabled")), "duet_disabled": bool(info.get("duet_disabled")),
            "stitch_disabled": bool(info.get("stitch_disabled")),
            "max_seconds": int(info.get("max_video_post_duration_sec") or 600),
        })


class RetryView(APIView):
    def post(self, request, post_id):
        require(request, "publish_posts")
        post = get_object_or_404(Post, id=post_id, workspace=get_membership(request).workspace)
        if post.status not in ("failed", "partial"):
            return Response({"detail": "Only failed posts can be retried."}, status=400)
        retry_failed(post)
        publish_in_background(post.id)
        return Response({"ok": True})

