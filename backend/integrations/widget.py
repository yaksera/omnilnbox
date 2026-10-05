"""Public API for the website chat widget (no login; each visitor gets a signed token)."""
import uuid

from django.core import signing
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from inbox.media import message_files, sniff
from inbox.models import Contact, Conversation
from inbox.services import ingest_message

from .models import ChannelAccount
from .providers import IncomingMessage
from .providers.website import WebsiteProvider

SALT = "omni.widget-visitor"

# Anti-abuse limits for the public widget. The AI budget itself is enforced per channel in automations.engine.
SESSIONS_PER_IP_HOUR = 30   # new visitor ids per IP (stops minting fresh visitors to dodge per-visitor limits)
MSGS_PER_VISITOR_MIN = 8
MSGS_PER_VISITOR_DAY = 120
MSGS_PER_IP_DAY = 200


def client_ip(request):
    """The visitor's IP as DRF sees it (honours REST_FRAMEWORK["NUM_PROXIES"])."""
    return BaseThrottle().get_ident(request) or "unknown"


def _over(key, limit, seconds):
    """Count one hit on `key`; True once the count goes past `limit` within the window."""
    key = f"omni:widget:{key}"
    if cache.add(key, 1, seconds):
        return limit < 1
    try:
        return cache.incr(key) > limit
    except ValueError:  # expired between add() and incr()
        cache.set(key, 1, seconds)
        return False


def _slow_down(detail="You're sending messages too quickly. Please wait a moment and try again."):
    return Response({"detail": detail}, status=429)


def _channel(channel_id):
    return get_object_or_404(ChannelAccount.objects.select_related("workspace"), id=channel_id, provider="website",
                             workspace__suspended_at__isnull=True,
                             status__in=[ChannelAccount.STATUS_ACTIVE, ChannelAccount.STATUS_PENDING])


def _visitor(request, channel):
    token = request.headers.get("X-Visitor-Token") or (request.data.get("token") if request.method == "POST" else "")
    try:
        data = signing.loads(token or "", salt=SALT)
    except signing.BadSignature:
        return None
    return data["v"] if data.get("c") == str(channel.id) else None


class WidgetBase(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "widget"


def _brand(ws):
    from core.serializers import WorkspaceSerializer
    return WorkspaceSerializer(ws).data["brand"]


class WidgetConfigView(WidgetBase):
    def get(self, request, channel_id):
        ch = _channel(channel_id)
        c = ch.credentials or {}
        from automations.models import AssistantSettings
        return Response({"title": c.get("title") or "Chat with us", "greeting": c.get("greeting") or "Hi! How can we help?",
                         "color": c.get("color") or "#4f46e5", "ask_contact": c.get("ask_contact") or "optional",
                         "max_chars": WebsiteProvider.limits(c)["max_chars"],
                         "shop": ch.workspace.name, "online": AssistantSettings.for_workspace(ch.workspace).is_open(),
                         "brand": _brand(ch.workspace)})


class SessionIn(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True)


class WidgetSessionView(WidgetBase):
    def post(self, request, channel_id):
        ch = _channel(channel_id)
        ser = SessionIn(data=request.data)
        ser.is_valid(raise_exception=True)
        visitor = _visitor(request, ch)
        if not visitor:
            if _over(f"sess:{ch.id}:{client_ip(request)}", SESSIONS_PER_IP_HOUR, 3600):
                return _slow_down("Too many new chats from your network. Please try again later.")
            visitor = uuid.uuid4().hex
        d = ser.validated_data
        contact = Contact.objects.filter(channel=ch, external_id=visitor).first()
        if contact and (d.get("name") or d.get("phone") or d.get("email")):
            contact.name = d.get("name") or contact.name
            contact.handle = d.get("phone") or d.get("email") or contact.handle
            contact.save(update_fields=["name", "handle"])
        return Response({"token": signing.dumps({"c": str(ch.id), "v": visitor}, salt=SALT), "visitor": visitor,
                         "profile": {k: v for k, v in d.items() if v}})


class MessageIn(serializers.Serializer):
    text = serializers.CharField(max_length=4000, trim_whitespace=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    contact = serializers.CharField(required=False, allow_blank=True, max_length=120)


class WidgetMessagesView(WidgetBase):
    def get(self, request, channel_id):
        ch = _channel(channel_id)
        visitor = _visitor(request, ch)
        if not visitor:
            return Response({"detail": "Start a session first."}, status=401)
        conv = Conversation.objects.filter(channel=ch, external_thread_id=visitor).first()
        if conv is None:
            return Response([])
        msgs = conv.messages.filter(is_note=False).order_by("sent_at", "created_at").prefetch_related("files")
        after = parse_datetime(request.query_params.get("after") or "")
        if after:
            msgs = msgs.filter(created_at__gt=after)
        return Response([{"id": str(m.id), "from": "visitor" if m.direction == "in" else ("bot" if m.bot else "agent"),
                          "name": m.sender_name if m.direction == "out" else "", "text": m.text,
                          "at": m.sent_at, "created_at": m.created_at,
                          "files": [f for f in message_files(m) if f["status"] == "ready"]} for m in msgs[:200]])

    def post(self, request, channel_id):
        ch = _channel(channel_id)
        visitor = _visitor(request, ch)
        if not visitor:
            return Response({"detail": "Start a session first."}, status=401)
        ser = MessageIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        max_chars = WebsiteProvider.limits(ch.credentials)["max_chars"]
        if len(d["text"]) > max_chars:
            return Response({"text": [f"Please keep messages under {max_chars} characters."],
                             "detail": f"Please keep messages under {max_chars} characters."}, status=400)
        ip = client_ip(request)
        if (_over(f"vmin:{visitor}", MSGS_PER_VISITOR_MIN, 60) or _over(f"vday:{visitor}", MSGS_PER_VISITOR_DAY, 86400)
                or _over(f"ipday:{ch.id}:{ip}", MSGS_PER_IP_DAY, 86400)):
            return _slow_down()
        msg = ingest_message(ch, IncomingMessage(
            external_thread_id=visitor, contact_external_id=visitor,
            contact_name=d.get("name") or f"Website visitor {visitor[:4].upper()}",
            contact_handle=d.get("contact") or "", text=d["text"],
            external_message_id=f"web-in-{uuid.uuid4().hex}", subject="",
            thread_meta={"page": str(request.headers.get("X-Page-Url", ""))[:300]},
        ))
        return Response({"id": str(msg.id) if msg else None, "at": msg.sent_at if msg else None}, status=201)



VISITOR_FILE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
VISITOR_MAX_BYTES = 5 * 1024 * 1024
VISITOR_FILES_PER_HOUR = 10


class WidgetUploadView(WidgetBase):
    """Visitors can send a photo or PDF (e.g. a screenshot of a product or a payment receipt)."""

    def post(self, request, channel_id):
        ch = _channel(channel_id)
        visitor = _visitor(request, ch)
        if not visitor:
            return Response({"detail": "Start a session first."}, status=401)
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "Choose a file."}, status=400)
        if f.size > VISITOR_MAX_BYTES:
            return Response({"detail": "Files can be at most 5 MB."}, status=400)
        data = f.read()
        mime = sniff(data[:64], "")
        if mime not in VISITOR_FILE_TYPES:
            return Response({"detail": "You can send photos (JPG, PNG, WebP) or PDF files."}, status=400)
        if _over(f"vfile:{visitor}", VISITOR_FILES_PER_HOUR, 3600) or _over(f"ipday:{ch.id}:{client_ip(request)}", MSGS_PER_IP_DAY, 86400):
            return _slow_down()
        caption = str(request.data.get("text") or "")[:WebsiteProvider.limits(ch.credentials)["max_chars"]]
        msg = ingest_message(ch, IncomingMessage(
            external_thread_id=visitor, contact_external_id=visitor,
            contact_name=str(request.data.get("name") or "")[:120] or f"Website visitor {visitor[:4].upper()}",
            text=caption, external_message_id=f"web-in-{uuid.uuid4().hex}",
            attachments=[{"type": "image" if mime.startswith("image/") else "file", "mime": mime,
                          "name": (f.name or "file")[:120], "data": data}],
        ))
        return Response({"id": str(msg.id) if msg else None}, status=201)


class WidgetSiteView(WidgetBase):
    """Which website-chat channel to show on OmniInbox's own marketing site (set by `manage.py setup_site_chat`)."""

    throttle_scope = "widget_site"  # every marketing page asks once; cached, so a generous separate limit

    def get(self, request):
        key = "omni:widget:site-channel"
        channel = cache.get(key)
        if channel is None:
            ch = (ChannelAccount.objects.filter(provider="website", state__site_chat=True,
                                                status__in=[ChannelAccount.STATUS_ACTIVE, ChannelAccount.STATUS_PENDING])
                  .order_by("-created_at").first())
            channel = str(ch.id) if ch else ""
            if channel:  # don't cache "none": the setup command runs in another process and can't clear this cache
                cache.set(key, channel, 60)
        return Response({"channel": channel or None})
