from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit import audit
from billing.plans import F_BROADCASTS
from core.permissions import require, require_feature
from core.tenancy import get_membership
from integrations.providers import ProviderError, get_provider

from . import services
from .models import Broadcast


def _m(request, write=False):
    m = require(request, "send_broadcasts") if write else get_membership(request)
    require_feature(m.workspace, F_BROADCASTS)
    return m


def broadcast_json(b, detail=False):
    data = {"id": str(b.id), "name": b.name, "channel": {"id": str(b.channel_id), "provider": b.channel.provider, "name": b.channel.name},
            "kind": b.kind, "text": b.text, "template_name": b.template_name, "template_language": b.template_language,
            "template_body": b.template_body, "variables": b.variables, "audience": b.audience, "status": b.status,
            "total": b.total, "sent": b.sent, "failed": b.failed, "created_at": b.created_at, "started_at": b.started_at,
            "finished_at": b.finished_at, "created_by": (b.created_by.get_full_name() or b.created_by.email) if b.created_by else ""}
    if detail:
        data["errors"] = list(b.recipients.filter(status="failed").values("conversation__contact__name", "error")[:20])
    return data


class BroadcastIn(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    channel_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["text", "template"])
    text = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    template_name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    template_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    template_body = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    variables = serializers.ListField(child=serializers.CharField(max_length=500, allow_blank=True), required=False, max_length=10)
    audience = serializers.DictField(required=False)

    def validate(self, data):
        ws = self.context["workspace"]
        ch = ws.channels.filter(id=data["channel_id"], is_demo=False).first() or (
            ws.channels.filter(id=data["channel_id"]).first() if self.context.get("allow_demo") else None)
        if ch is None:
            raise serializers.ValidationError({"channel_id": "Pick one of your connected channels."})
        rule = services.RULES.get(ch.provider)
        if rule is None:
            raise serializers.ValidationError({"channel_id": "Broadcasts work on WhatsApp, Telegram, Viber, Messenger and Instagram."})
        if data["kind"] not in rule["kinds"]:
            raise serializers.ValidationError({"kind": rule["note"]})
        if data["kind"] == "text" and not (data.get("text") or "").strip():
            raise serializers.ValidationError({"text": "Write the message."})
        if data["kind"] == "template" and not (data.get("template_name") and data.get("template_language")):
            raise serializers.ValidationError({"template_name": "Choose an approved template."})
        data["channel"] = ch
        return data


class BroadcastsView(APIView):
    def get(self, request):
        m = _m(request)
        return Response([broadcast_json(b) for b in Broadcast.objects.filter(workspace=m.workspace).select_related("channel", "created_by")[:100]])

    def post(self, request):
        m = _m(request, write=True)
        ser = BroadcastIn(data=request.data, context={"workspace": m.workspace, "allow_demo": True})
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        d.pop("channel_id")
        b = Broadcast.objects.create(workspace=m.workspace, created_by=request.user, **d)
        return Response(broadcast_json(b), status=201)


class AudienceView(APIView):
    def post(self, request):
        m = _m(request)
        ch = get_object_or_404(m.workspace.channels, id=request.data.get("channel_id"))
        rule = services.RULES.get(ch.provider)
        if rule is None:
            return Response({"count": 0, "note": "This channel doesn't support broadcasts."})
        qs = services.audience(m.workspace, ch, request.data.get("audience") or {})
        return Response({"count": qs.count(), "sample": [c.contact.name or c.contact.handle for c in qs[:5]],
                         "note": rule["note"], "kinds": rule["kinds"],
                         "opted_out": ch.contacts.filter(opted_out=True).count()})


class TemplatesView(APIView):
    def get(self, request):
        m = _m(request)
        ch = get_object_or_404(m.workspace.channels, id=request.query_params.get("channel"), provider="whatsapp")
        provider = get_provider(ch)
        if not hasattr(provider, "templates") or ch.is_demo:
            return Response([{"name": "order_update", "language": "en", "status": "APPROVED", "category": "UTILITY",
                              "body": "Hi {{1}}, your order {{2}} is ready. Reply to this message for details.", "variables": 2,
                              "media_header": False}])  # demo channels: a sample template
        try:
            return Response([t for t in provider.templates() if t["status"] == "APPROVED"])
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=400)


class BroadcastDetailView(APIView):
    def get(self, request, pk):
        m = _m(request)
        return Response(broadcast_json(get_object_or_404(Broadcast.objects.select_related("channel"), workspace=m.workspace, pk=pk), True))

    def delete(self, request, pk):
        m = _m(request, write=True)
        b = get_object_or_404(Broadcast, workspace=m.workspace, pk=pk, status="draft")
        b.delete()
        return Response(status=204)


class BroadcastActionView(APIView):
    def post(self, request, pk, action):
        m = _m(request, write=True)
        b = get_object_or_404(Broadcast.objects.select_related("channel"), workspace=m.workspace, pk=pk)
        if action == "send":
            if b.status != "draft":
                return Response({"detail": "This broadcast was already sent."}, status=400)
            services.start(b)
            audit(request, "broadcast.sent", target=b.name, meta={"recipients": b.total, "channel": b.channel.name})
        elif action == "cancel":
            if b.status == "sending":
                b.status = "cancelled"
                b.save(update_fields=["status"])
                b.recipients.filter(status="pending").update(status="skipped", error="Cancelled")
        else:
            return Response({"detail": "Unknown action."}, status=404)
        b.refresh_from_db()
        return Response(broadcast_json(b, True))
