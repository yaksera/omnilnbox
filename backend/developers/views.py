from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit import audit
from billing.plans import F_API, F_WHITE_LABEL
from core.permissions import require, require_feature
from publishing import media as media_utils
from publishing.models import MediaAsset

from . import events
from .models import EVENTS, ApiKey, WebhookEndpoint


def _m(request, feature=F_API):
    m = require(request, "manage_developers")
    require_feature(m.workspace, feature)
    return m


def key_json(k):
    return {"id": str(k.id), "name": k.name, "prefix": k.prefix, "created_at": k.created_at, "last_used_at": k.last_used_at,
            "created_by": k.created_by.get_full_name() or k.created_by.email, "revoked": bool(k.revoked_at)}


def hook_json(h, with_secret=False):
    data = {"id": str(h.id), "url": h.url, "events": h.events, "active": h.active, "failures": h.failures,
            "last_status": h.last_status, "last_error": h.last_error, "last_delivery_at": h.last_delivery_at, "created_at": h.created_at}
    if with_secret:
        data["secret"] = h.secret
    return data


class ApiKeysView(APIView):
    def get(self, request):
        m = _m(request)
        return Response([key_json(k) for k in ApiKey.objects.filter(workspace=m.workspace, revoked_at__isnull=True).select_related("created_by")])

    def post(self, request):
        m = _m(request)
        name = str(request.data.get("name") or "").strip()[:80] or "API key"
        if ApiKey.objects.filter(workspace=m.workspace, revoked_at__isnull=True).count() >= 20:
            return Response({"detail": "Up to 20 active keys. Revoke one first."}, status=400)
        key, raw = ApiKey.issue(m.workspace, request.user, name)
        audit(request, "api_key.created", target=name)
        return Response({**key_json(key), "key": raw}, status=201)  # shown once


class ApiKeyDetailView(APIView):
    def delete(self, request, pk):
        m = _m(request)
        key = get_object_or_404(ApiKey, workspace=m.workspace, pk=pk, revoked_at__isnull=True)
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        audit(request, "api_key.revoked", target=key.name)
        return Response(status=204)


class HookIn(serializers.Serializer):
    url = serializers.URLField(max_length=500)
    events = serializers.ListField(child=serializers.ChoiceField(choices=list(EVENTS)), min_length=1)
    active = serializers.BooleanField(required=False, default=True)

    def validate_url(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError("Use an https:// URL.")
        return value


class WebhooksView(APIView):
    def get(self, request):
        m = _m(request)
        return Response({"events": EVENTS, "endpoints": [hook_json(h, True) for h in WebhookEndpoint.objects.filter(workspace=m.workspace)]})

    def post(self, request):
        m = _m(request)
        ser = HookIn(data=request.data)
        ser.is_valid(raise_exception=True)
        if WebhookEndpoint.objects.filter(workspace=m.workspace).count() >= 10:
            return Response({"detail": "Up to 10 webhook endpoints."}, status=400)
        h = WebhookEndpoint.objects.create(workspace=m.workspace, **ser.validated_data)
        audit(request, "webhook.created", target=h.url)
        return Response(hook_json(h, True), status=201)


class WebhookDetailView(APIView):
    def _get(self, request, pk):
        m = _m(request)
        return get_object_or_404(WebhookEndpoint, workspace=m.workspace, pk=pk)

    def put(self, request, pk):
        h = self._get(request, pk)
        ser = HookIn(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        for k, v in ser.validated_data.items():
            setattr(h, k, v)
        if ser.validated_data.get("active"):
            h.failures = 0
        h.save()
        return Response(hook_json(h, True))

    def delete(self, request, pk):
        h = self._get(request, pk)
        audit(request, "webhook.deleted", target=h.url)
        h.delete()
        return Response(status=204)


class WebhookTestView(APIView):
    throttle_scope = "send"

    def post(self, request, pk):
        m = _m(request)
        h = get_object_or_404(WebhookEndpoint, workspace=m.workspace, pk=pk)
        payload = {"id": "test", "event": "ping", "created_at": timezone.now().isoformat(), "workspace_id": str(m.workspace.id),
                   "data": {"message": "Hello from OmniInbox! Your webhook works."}}
        d = events.deliver_now(h, "ping", payload, retries=(0,))
        h.refresh_from_db()
        return Response({"ok": d.status_code is not None and d.status_code < 300, "status": d.status_code, "error": d.error,
                         "endpoint": hook_json(h, True)})


class WebhookDeliveriesView(APIView):
    def get(self, request, pk):
        m = _m(request)
        h = get_object_or_404(WebhookEndpoint, workspace=m.workspace, pk=pk)
        return Response([{"id": d.id, "event": d.event, "status": d.status_code, "error": d.error, "attempts": d.attempts,
                          "duration_ms": d.duration_ms, "created_at": d.created_at} for d in h.deliveries.all()[:50]])


class BrandView(APIView):
    """White-label: PUT {brand_name, brand_color, hide_powered_by}; POST multipart {file} for the logo; DELETE removes the logo."""

    parser_classes = [MultiPartParser, *APIView.parser_classes]

    def _m(self, request):
        m = require(request, "manage_settings")
        require_feature(m.workspace, F_WHITE_LABEL)
        return m

    def _json(self, ws):
        from core.serializers import WorkspaceSerializer
        return WorkspaceSerializer(ws).data["brand"]

    def put(self, request):
        import re
        ws = self._m(request).workspace
        color = str(request.data.get("brand_color", ws.brand_color) or "")
        if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return Response({"brand_color": ["Use a hex colour like #0f766e."]}, status=400)
        ws.brand_name = str(request.data.get("brand_name", ws.brand_name) or "")[:60]
        ws.brand_color = color
        if "hide_powered_by" in request.data:
            ws.hide_powered_by = str(request.data["hide_powered_by"]).lower() in ("1", "true", "yes")
        ws.save(update_fields=["brand_name", "brand_color", "hide_powered_by"])
        return Response(self._json(ws))

    def post(self, request):
        m = self._m(request)
        f = request.FILES.get("file")
        if f is None:
            return Response({"file": ["Choose an image."]}, status=400)
        head = f.read(16)
        f.seek(0)
        mime = media_utils.sniff(head)
        if mime not in media_utils.IMAGE_TYPES or f.size > 2 * 1024 * 1024:
            return Response({"file": ["Upload a PNG or JPEG logo up to 2 MB."]}, status=400)
        asset = MediaAsset(workspace=m.workspace, kind="image", mime=mime, size=f.size, original_name=f.name[:255], uploaded_by=request.user)
        asset.file.save(f"logo.{media_utils.IMAGE_TYPES[mime]}", f, save=False)
        asset.save()
        m.workspace.brand_logo = asset
        m.workspace.save(update_fields=["brand_logo"])
        return Response(self._json(m.workspace), status=201)

    def delete(self, request):
        ws = self._m(request).workspace
        ws.brand_logo = None
        ws.save(update_fields=["brand_logo"])
        return Response(self._json(ws))
