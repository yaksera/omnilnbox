"""One-click "Connect with Facebook" for WhatsApp, Messenger and Instagram.

You (the OmniInbox operator) create ONE Meta app and put its details in the backend .env:
    META_APP_ID, META_APP_SECRET, META_VERIFY_TOKEN
    META_WA_CONFIG_ID     - WhatsApp Embedded Signup configuration (Facebook Login for Business)
    META_PAGES_CONFIG_ID  - Facebook Login for Business configuration for Pages + Instagram messaging
Customers then click "Connect with Facebook", pick their business / number / Page in Meta's own popup,
and OmniInbox receives a code, swaps it for tokens server-side and creates the channels.

All customers share one webhook for that app: /api/webhooks/meta/ (set it once in the Meta app).
Messages are routed to the right channel by phone number id / Page id / Instagram account id.
"""
import hashlib
import hmac
import json
import logging
import secrets

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit import audit
from core.permissions import require
from inbox.services import ingest_message

from .models import ChannelAccount
from .providers import ProviderError, get_provider
from .providers.meta import GRAPH_VERSION

logger = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com"
SESSION_TTL = 900  # the list of Pages waits 15 minutes for the customer to pick


def _cfg(name):
    return (getattr(settings, name, "") or "").strip()


def enabled(kind):
    base = _cfg("META_APP_ID") and _cfg("META_APP_SECRET")
    return bool(base and _cfg("META_WA_CONFIG_ID" if kind == "whatsapp" else "META_PAGES_CONFIG_ID"))


def graph(method, path, token=None, **kwargs):
    params = kwargs.pop("params", {}) or {}
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        params["appsecret_proof"] = hmac.new(_cfg("META_APP_SECRET").encode(), token.encode(), hashlib.sha256).hexdigest()
    resp = requests.request(method, f"{GRAPH}/{GRAPH_VERSION}/{path.lstrip('/')}", params=params, headers=headers,
                            timeout=30, **kwargs)
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text[:300]}
    if resp.status_code >= 400:
        err = (data.get("error") or {}) if isinstance(data, dict) else {}
        raise ProviderError(f"Facebook: {err.get('message') or resp.status_code}", status=resp.status_code, detail=data)
    return data


def exchange_code(code):
    """Swap the code from Meta's popup for an access token (server-side: the app secret never leaves the server)."""
    params = {"client_id": _cfg("META_APP_ID"), "client_secret": _cfg("META_APP_SECRET"), "code": code}
    try:
        data = graph("GET", "oauth/access_token", params=params)
    except ProviderError as exc:
        if "redirect_uri" not in str(exc):
            raise
        # Codes from the JS SDK popup are sometimes bound to an empty redirect_uri
        data = graph("GET", "oauth/access_token", params={**params, "redirect_uri": ""})
    token = data.get("access_token")
    if not token:
        raise ProviderError("Facebook didn't return an access token. Please try again.")
    return token


def _check_limit(ws, adding):
    have = ChannelAccount.objects.filter(workspace=ws, is_demo=False).count()
    if have + adding > ws.channel_limit:
        raise ValidationError({"detail": f"Your {ws.plan_info['name']} plan allows {ws.channel_limit} channels "
                                         f"(you have {have}). Upgrade on the Billing page to add more."})


def _existing(ws, provider, meta_id):
    return ChannelAccount.objects.filter(workspace=ws, provider=provider, state__meta_id=str(meta_id)).first()


class MetaConfigView(APIView):
    def get(self, request):
        return Response({"app_id": _cfg("META_APP_ID"), "graph_version": GRAPH_VERSION,
                         "whatsapp": {"enabled": enabled("whatsapp"), "config_id": _cfg("META_WA_CONFIG_ID")},
                         "pages": {"enabled": enabled("pages"), "config_id": _cfg("META_PAGES_CONFIG_ID")}})


class WhatsAppIn(serializers.Serializer):
    code = serializers.CharField(max_length=2000)
    # Normally sent by the Embedded Signup popup; if the browser didn't get them we look them up from the token
    waba_id = serializers.RegexField(r"^[A-Za-z0-9_]{1,40}$", required=False, allow_blank=True)
    phone_number_id = serializers.RegexField(r"^[A-Za-z0-9_]{1,40}$", required=False, allow_blank=True)
    pin = serializers.RegexField(r"^\d{6}$", required=False, allow_blank=True)


NO_WA_NUMBER = ("Facebook didn't share a WhatsApp number. Check that META_WA_CONFIG_ID is a configuration made with "
                "the 'WhatsApp Embedded Signup' login variation, then try again and add or pick a phone number in the "
                "Facebook window.")


def discover_whatsapp(token):
    """Which WhatsApp Business account + number did the person share? (from the token's granted targets)"""
    info = graph("GET", "debug_token", params={
        "input_token": token, "access_token": f"{_cfg('META_APP_ID')}|{_cfg('META_APP_SECRET')}"}).get("data") or {}
    wabas = []
    for scope in info.get("granular_scopes") or []:
        if scope.get("scope") in ("whatsapp_business_management", "whatsapp_business_messaging"):
            wabas += [str(t) for t in scope.get("target_ids") or [] if str(t) not in wabas]
    numbers = []
    for waba in wabas:
        for n in graph("GET", f"{waba}/phone_numbers", token, params={"fields": "id"}).get("data") or []:
            numbers.append((waba, str(n["id"])))
    if not numbers:
        raise ProviderError(NO_WA_NUMBER)
    if len(numbers) > 1:
        raise ProviderError("Several WhatsApp numbers were shared. Please try again and pick just one number.")
    return numbers[0]


class WhatsAppConnectView(APIView):
    """After Embedded Signup: {code, waba_id, phone_number_id, pin} -> a ready WhatsApp channel."""

    throttle_scope = "auth"

    def post(self, request):
        m = require(request, "manage_channels")
        if not enabled("whatsapp"):
            return Response({"detail": "Connect with Facebook isn't set up on this server yet."}, status=400)
        ser = WhatsAppIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        ws = m.workspace
        try:
            token = exchange_code(d["code"])
            if not (d.get("waba_id") and d.get("phone_number_id")):
                d["waba_id"], d["phone_number_id"] = discover_whatsapp(token)
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=400)
        channel = _existing(ws, "whatsapp", d["phone_number_id"])
        if not channel:
            _check_limit(ws, 1)
        try:
            info = graph("GET", d["phone_number_id"], token, params={"fields": "display_phone_number,verified_name"})
            graph("POST", f"{d['waba_id']}/subscribed_apps", token)  # send this number's messages to our webhook
            if d.get("pin"):
                try:
                    graph("POST", f"{d['phone_number_id']}/register", token,
                          json={"messaging_product": "whatsapp", "pin": d["pin"]})
                except ProviderError as exc:
                    if "already registered" not in str(exc).lower():
                        raise
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=400)
        creds = {"access_token": token, "phone_number_id": d["phone_number_id"], "business_account_id": d["waba_id"],
                 "app_secret": _cfg("META_APP_SECRET"), "verify_token": _cfg("META_VERIFY_TOKEN")}
        name = info.get("verified_name") or info.get("display_phone_number") or "WhatsApp"
        if channel:
            channel.credentials = {**channel.credentials, **creds}
        else:
            channel = ChannelAccount(workspace=ws, provider="whatsapp", name=name[:120], credentials=creds,
                                     created_by=request.user)
        channel.state = {**channel.state, "meta_id": d["phone_number_id"], "via_facebook": True,
                         "account_info": {"phone": info.get("display_phone_number"), "name": info.get("verified_name")}}
        channel.status, channel.last_error = ChannelAccount.STATUS_ACTIVE, ""
        channel.save()
        audit(request, "channel.connected", target=f"WhatsApp: {channel.name} (Connect with Facebook)")
        from .serializers import ChannelAccountSerializer
        return Response(ChannelAccountSerializer(channel).data, status=201)


class PagesIn(serializers.Serializer):
    # access_token: from the Facebook JS SDK popup (no redirect_uri involved). code: older clients.
    access_token = serializers.CharField(max_length=2000, required=False)
    code = serializers.CharField(max_length=2000, required=False)

    def validate(self, attrs):
        if not attrs.get("access_token") and not attrs.get("code"):
            raise serializers.ValidationError({"detail": "Log in with Facebook first."})
        return attrs


def token_info(token):
    """A user token handed over by the browser: make sure Facebook issued it to OUR app and it's still valid."""
    info = graph("GET", "debug_token", params={
        "input_token": token, "access_token": f"{_cfg('META_APP_ID')}|{_cfg('META_APP_SECRET')}"}).get("data") or {}
    if not info.get("is_valid") or str(info.get("app_id")) != str(_cfg("META_APP_ID")):
        raise ProviderError("Facebook login wasn't valid for this app. Please try again.")
    return info


def verify_user_token(token):
    token_info(token)
    return token


def long_lived(user_token):
    """Short-lived user token -> long-lived one; Page tokens fetched with it never expire."""
    return graph("GET", "oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": _cfg("META_APP_ID"),
        "client_secret": _cfg("META_APP_SECRET"), "fb_exchange_token": user_token}).get("access_token") or user_token


def publish_login_config():
    """What the Publish page needs for one-click 'Continue with Facebook' (None if not set up)."""
    config_id = _cfg("META_PUBLISH_CONFIG_ID") or _cfg("META_PAGES_CONFIG_ID")
    if not (_cfg("META_APP_ID") and _cfg("META_APP_SECRET") and config_id):
        return None
    return {"app_id": _cfg("META_APP_ID"), "graph_version": GRAPH_VERSION, "config_id": config_id}


class PagesListView(APIView):
    """{code} from Facebook Login -> the Pages (and linked Instagram accounts) the person manages."""

    throttle_scope = "auth"

    def post(self, request):
        m = require(request, "manage_channels")
        if not enabled("pages"):
            return Response({"detail": "Connect with Facebook isn't set up on this server yet."}, status=400)
        ser = PagesIn(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            d = ser.validated_data
            user_token = verify_user_token(d["access_token"]) if d.get("access_token") else exchange_code(d["code"])
            # long-lived user token -> Page tokens that don't expire
            long = graph("GET", "oauth/access_token", params={
                "grant_type": "fb_exchange_token", "client_id": _cfg("META_APP_ID"),
                "client_secret": _cfg("META_APP_SECRET"), "fb_exchange_token": user_token}).get("access_token") or user_token
            data = graph("GET", "me/accounts", long, params={
                "fields": "id,name,access_token,picture{url},instagram_business_account{id,username,profile_picture_url}",
                "limit": "100"})
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=400)
        pages = data.get("data", [])
        if not pages:
            return Response({"detail": "No Facebook Pages were shared. In the Facebook window, choose the Pages "
                                       "(and Instagram accounts) you want to connect."}, status=400)
        session = secrets.token_urlsafe(24)
        cache.set(f"omni:meta-pages:{session}", {"ws": str(m.workspace_id), "user": request.user.id, "pages": pages},
                  SESSION_TTL)
        ws = m.workspace
        out = []
        for p in pages:
            ig = p.get("instagram_business_account") or None
            out.append({"id": p["id"], "name": p.get("name", ""), "picture": ((p.get("picture") or {}).get("data") or {}).get("url", ""),
                        "connected": bool(_existing(ws, "messenger", p["id"])),
                        "instagram": {"id": ig["id"], "username": ig.get("username", ""),
                                      "connected": bool(_existing(ws, "instagram", ig["id"]))} if ig else None})
        return Response({"session": session, "pages": out})


class PagesConnectIn(serializers.Serializer):
    session = serializers.CharField(max_length=100)
    pages = serializers.ListField(child=serializers.RegexField(r"^[A-Za-z0-9_]{1,40}$"), required=False, default=list, max_length=50)
    instagram = serializers.ListField(child=serializers.RegexField(r"^[A-Za-z0-9_]{1,40}$"), required=False, default=list, max_length=50)


class PagesConnectView(APIView):
    """Create Messenger / Instagram channels for the Pages the customer ticked."""

    def post(self, request):
        m = require(request, "manage_channels")
        ser = PagesConnectIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        stash = cache.get(f"omni:meta-pages:{d['session']}")
        if not stash or stash["ws"] != str(m.workspace_id) or stash["user"] != request.user.id:
            return Response({"detail": "This Facebook session expired. Click Connect with Facebook again."}, status=400)
        ws = m.workspace
        wanted = [("messenger", p) for p in stash["pages"] if p["id"] in d["pages"]]
        wanted += [("instagram", p) for p in stash["pages"]
                   if (p.get("instagram_business_account") or {}).get("id") in d["instagram"]]
        if not wanted:
            return Response({"detail": "Tick at least one Page or Instagram account."}, status=400)
        new = sum(1 for kind, p in wanted if not _existing(
            ws, kind, p["id"] if kind == "messenger" else p["instagram_business_account"]["id"]))
        _check_limit(ws, new)
        from .serializers import ChannelAccountSerializer
        from .views import _connect
        created = []
        for kind, p in wanted:
            ig = p.get("instagram_business_account") or {}
            meta_id = p["id"] if kind == "messenger" else ig["id"]
            creds = {"page_access_token": p["access_token"], "app_secret": _cfg("META_APP_SECRET"),
                     "verify_token": _cfg("META_VERIFY_TOKEN")}
            if kind == "messenger":
                creds["page_id"], name = p["id"], p.get("name") or "Facebook Page"
            else:
                creds["ig_account_id"], name = ig["id"], f"@{ig.get('username')}" if ig.get("username") else p.get("name", "Instagram")
            channel = _existing(ws, kind, meta_id) or ChannelAccount(workspace=ws, provider=kind, name=name[:120],
                                                                     created_by=request.user)
            channel.credentials = {**(channel.credentials or {}), **creds}
            channel.state = {**channel.state, "meta_id": meta_id, "via_facebook": True}
            channel.save()
            _connect(channel)  # verifies the token and subscribes the Page to our webhook
            audit(request, "channel.connected", target=f"{channel.get_provider_display()}: {channel.name} (Connect with Facebook)")
            created.append(channel)
        cache.delete(f"omni:meta-pages:{d['session']}")
        return Response(ChannelAccountSerializer(created, many=True).data, status=201)


# ------------------------------------------------------------------ one webhook for every customer
class _Req:
    """What provider.parse_webhook needs from a request, for one channel's slice of a shared webhook."""

    def __init__(self, body, headers):
        self.body, self.headers, self.GET = body, headers, {}


def _entry_ids(obj, entry):
    if obj == "whatsapp_business_account":
        return {str((c.get("value") or {}).get("metadata", {}).get("phone_number_id", "")) for c in entry.get("changes", [])}
    return {str(entry.get("id", ""))}


def _channels_for(provider, meta_id):
    qs = ChannelAccount.objects.select_related("workspace").filter(provider=provider, is_demo=False).exclude(
        status=ChannelAccount.STATUS_DISABLED)
    found = list(qs.filter(state__meta_id=meta_id))
    if found:
        return found
    # channels connected by pasting tokens (before one-click existed): match on the stored id, then remember it
    key = {"whatsapp": "phone_number_id", "messenger": "page_id", "instagram": "ig_account_id"}[provider]
    for ch in qs.filter(state__meta_id__isnull=True):
        if str((ch.credentials or {}).get(key, "")).strip() == meta_id:
            ch.state = {**ch.state, "meta_id": meta_id}
            ch.save(update_fields=["state"])
            found.append(ch)
    return found


@csrf_exempt
@require_http_methods(["GET", "POST"])
def meta_webhook(request):
    """/api/webhooks/meta/ - the single callback URL of the OmniInbox Meta app."""
    if request.method == "GET":
        if request.GET.get("hub.mode") == "subscribe" and _cfg("META_VERIFY_TOKEN") and \
                hmac.compare_digest(request.GET.get("hub.verify_token", ""), _cfg("META_VERIFY_TOKEN")):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse("verify token mismatch", status=403)
    secret = _cfg("META_APP_SECRET")
    expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest() if secret else ""
    if not secret or not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", ""), expected):
        logger.warning("Rejected shared Meta webhook with a bad signature")
        return HttpResponse("invalid signature", status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"ok": True, "stored": 0})
    obj = body.get("object")
    provider = {"whatsapp_business_account": "whatsapp", "page": "messenger", "instagram": "instagram"}.get(obj)
    if not provider:
        return JsonResponse({"ok": True, "stored": 0})
    stored = 0
    for entry in body.get("entry", []):
        for meta_id in _entry_ids(obj, entry) - {""}:
            for channel in _channels_for(provider, meta_id):
                if channel.workspace.suspended_at:
                    continue
                raw = json.dumps({"object": obj, "entry": [entry]}).encode()
                try:
                    items = get_provider(channel).parse_webhook(_Req(raw, request.headers))
                    stored += sum(1 for item in items if ingest_message(channel, item))
                    if provider in ("messenger", "instagram"):
                        from automations.comments import handle_webhook
                        handle_webhook(channel, raw)
                except Exception:  # noqa: BLE001 - one bad channel must not block the others
                    logger.exception("Shared Meta webhook failed for %s", channel)
    return JsonResponse({"ok": True, "stored": stored})
