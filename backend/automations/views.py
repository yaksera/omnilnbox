from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.audit import audit

from billing.plans import F_AI, F_AI_BOT, F_AUTOMATIONS, F_ORDERS
from core.permissions import require, require_feature
from core.tenancy import get_membership
from inbox.models import Conversation, Tag
from inbox.views import visible_conversations

from . import ai, ingest, llm, search
from .models import DAYS, AssistantSettings, KnowledgeItem, KnowledgeSource, Rule

MAX_KNOWLEDGE = 300  # entries written by hand
MAX_SOURCES = 30  # uploaded documents + imported websites
MAX_RULES = 100


class AIThrottled(APIView):
    throttle_scope = "ai"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [*super().get_throttles(), ScopedRateThrottle()] if self.request.method == "POST" else super().get_throttles()


def _ai_call(fn, *args, **kwargs):
    try:
        return Response(fn(*args, **kwargs))
    except llm.AIError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def _conversation(request, conversation_id):
    import uuid
    from django.http import Http404
    try:
        uuid.UUID(str(conversation_id))
    except ValueError as exc:
        raise Http404 from exc
    ws = get_membership(request).workspace
    qs = visible_conversations(request, Conversation.objects.filter(workspace=ws))
    return get_object_or_404(qs.select_related("contact", "channel", "workspace"), id=conversation_id)


# ------------------------------------------------------------------ settings + usage
class SettingsIn(serializers.ModelSerializer):
    class Meta:
        model = AssistantSettings
        fields = ["business_name", "about", "tone", "bot_name", "bot_mode", "handoff_message", "auto_tag",
                  "timezone", "hours", "sales_orders", "sales_bookings", "booking_label", "booking_minutes",
                  "booking_capacity", "followup_enabled", "followup_hours", "voice_notes", "check_payments"]
        extra_kwargs = {"booking_minutes": {"min_value": 10, "max_value": 240},
                        "booking_capacity": {"min_value": 1, "max_value": 50},
                        "followup_hours": {"min_value": 1, "max_value": 47}}

    def validate_booking_label(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Give the visit a name, e.g. Counselling session.")
        return value

    def validate_timezone(self, value):
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(value)
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError("Unknown time zone.") from exc
        return value

    def validate_hours(self, value):
        import re
        if not isinstance(value, dict):
            raise serializers.ValidationError("Invalid hours.")
        clean = {}
        for d in DAYS:
            day = value.get(d) or {}
            start, end = str(day.get("start", "10:00")), str(day.get("end", "18:00"))
            if not (re.fullmatch(r"[0-2]\d:[0-5]\d", start) and re.fullmatch(r"[0-2]\d:[0-5]\d", end)):
                raise serializers.ValidationError(f"Use HH:MM times for {d}.")
            clean[d] = {"on": bool(day.get("on")), "start": start, "end": end}
        return clean


def _settings_json(cfg):
    ws = cfg.workspace
    return {
        **SettingsIn(cfg).data,
        "is_open": cfg.is_open(),
        "configured": llm.configured(),
        "model": settings.OPENROUTER_MODEL,
        "features": {"ai": ws.has_feature(F_AI), "automations": ws.has_feature(F_AUTOMATIONS),
                     "bot": ws.has_feature(F_AI_BOT), "orders": ws.has_feature(F_ORDERS)},
        "credits": ai.credits_status(ws),
        "knowledge_count": KnowledgeItem.objects.filter(workspace=ws).count(),
    }


class SettingsView(APIView):
    def get(self, request):
        return Response(_settings_json(AssistantSettings.for_workspace(get_membership(request).workspace)))

    def put(self, request):
        m = require(request, "manage_automations")
        cfg = AssistantSettings.for_workspace(m.workspace)
        ser = SettingsIn(cfg, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        if ser.validated_data.get("bot_mode", cfg.bot_mode) != AssistantSettings.BOT_OFF:
            require_feature(m.workspace, F_AI_BOT)
        if ser.validated_data.get("sales_orders"):
            require_feature(m.workspace, F_ORDERS)
        ser.save()
        audit(request, "ai.settings_changed", meta={"bot_mode": cfg.bot_mode, "auto_tag": cfg.auto_tag})
        return Response(_settings_json(cfg))


# ------------------------------------------------------------------ knowledge base
class KnowledgeIn(serializers.ModelSerializer):
    source = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeItem
        fields = ["id", "title", "content", "updated_at", "source"]
        read_only_fields = ["id", "updated_at", "source"]

    def get_source(self, obj):
        return {"id": obj.source_id, "name": obj.source.name, "kind": obj.source.kind} if obj.source_id else None


class KnowledgeView(APIView):
    def get(self, request):
        ws = get_membership(request).workspace
        return Response(KnowledgeIn(KnowledgeItem.objects.filter(workspace=ws).select_related("source"), many=True).data)

    def post(self, request):
        m = require(request, "manage_automations")
        if KnowledgeItem.objects.filter(workspace=m.workspace, source__isnull=True).count() >= MAX_KNOWLEDGE:
            return Response({"detail": f"You can write up to {MAX_KNOWLEDGE} entries by hand. Upload a document for more."}, status=400)
        ser = KnowledgeIn(data=request.data)
        ser.is_valid(raise_exception=True)
        item = ser.save(workspace=m.workspace)
        search.embed_items_async([item.id])
        return Response(ser.data, status=201)


class KnowledgeDetailView(APIView):
    def _get(self, request, pk):
        m = require(request, "manage_automations")
        return get_object_or_404(KnowledgeItem, workspace=m.workspace, pk=pk)

    def put(self, request, pk):
        ser = KnowledgeIn(self._get(request, pk), data=request.data)
        ser.is_valid(raise_exception=True)
        item = ser.save()
        search.embed_items_async([item.id])  # the meaning changed: refresh its embedding
        return Response(ser.data)

    def delete(self, request, pk):
        self._get(request, pk).delete()
        return Response(status=204)


# ------------------------------------------------------------------ imported documents & websites
def _source_json(s, count=None):
    return {"id": s.id, "kind": s.kind, "name": s.name, "url": s.url, "crawl": s.crawl, "status": s.status, "error": s.error,
            "pages": s.pages, "chars": s.chars, "entries": s.items.count() if count is None else count,
            "created_at": s.created_at, "updated_at": s.updated_at}


def _can_add_source(ws):
    if KnowledgeSource.objects.filter(workspace=ws).count() >= MAX_SOURCES:
        return Response({"detail": f"You can import up to {MAX_SOURCES} documents and websites. Delete one to add another."}, status=400)
    if KnowledgeSource.objects.filter(workspace=ws, status=KnowledgeSource.PROCESSING).count() >= 3:
        return Response({"detail": "Please wait for the current imports to finish."}, status=400)
    return None


class SourcesView(APIView):
    def get(self, request):
        from django.db.models import Count
        ws = get_membership(request).workspace
        rows = KnowledgeSource.objects.filter(workspace=ws).annotate(n=Count("items"))
        return Response([_source_json(s, s.n) for s in rows])


class SourceUploadView(APIView):
    """POST multipart {file}: a PDF, Word (.docx) or text file to read into the knowledge base."""

    def post(self, request):
        m = require(request, "manage_automations")
        require_feature(m.workspace, F_AI)
        f = request.FILES.get("file")
        if f is None:
            return Response({"detail": "Choose a file to upload."}, status=400)
        if f.size > ingest.MAX_FILE_BYTES:
            return Response({"detail": "The file is larger than 10 MB."}, status=400)
        name = (f.name or "document")[:255]
        if not name.lower().endswith((".pdf", ".docx", ".txt", ".md", ".csv")):
            return Response({"detail": "Upload a PDF, Word (.docx) or text (.txt) file."}, status=400)
        blocked = _can_add_source(m.workspace)
        if blocked:
            return blocked
        src = KnowledgeSource.objects.create(workspace=m.workspace, kind=KnowledgeSource.FILE, name=name, created_by=request.user)
        ingest.start_import(src, f.read())
        audit(request, "ai.knowledge_upload", target=name)
        return Response(_source_json(src, 0), status=201)


class SourceUrlIn(serializers.Serializer):
    url = serializers.URLField(max_length=1000)
    crawl = serializers.BooleanField(default=True)


class SourceUrlView(APIView):
    """POST {url, crawl}: import a website (and, with crawl, its About / Courses / Fees / FAQ... pages)."""

    def post(self, request):
        m = require(request, "manage_automations")
        require_feature(m.workspace, F_AI)
        ser = SourceUrlIn(data=request.data)
        ser.is_valid(raise_exception=True)
        blocked = _can_add_source(m.workspace)
        if blocked:
            return blocked
        url = ser.validated_data["url"]
        from urllib.parse import urlparse
        src = KnowledgeSource.objects.create(workspace=m.workspace, kind=KnowledgeSource.WEBSITE, url=url, crawl=ser.validated_data["crawl"],
                                             name=urlparse(url).hostname or url, created_by=request.user)
        ingest.start_import(src)
        audit(request, "ai.knowledge_website", target=url)
        return Response(_source_json(src, 0), status=201)


class SourceDetailView(APIView):
    def _get(self, request, pk):
        m = require(request, "manage_automations")
        return get_object_or_404(KnowledgeSource, workspace=m.workspace, pk=pk)

    def post(self, request, pk):
        """Re-import a website (picks up changes on the site). Edited entries are replaced."""
        src = self._get(request, pk)
        if src.kind != KnowledgeSource.WEBSITE:
            return Response({"detail": "To update a document, delete it and upload the new version."}, status=400)
        if src.status == KnowledgeSource.PROCESSING:
            return Response({"detail": "This website is already being imported."}, status=400)
        src.status, src.error = KnowledgeSource.PROCESSING, ""
        src.save(update_fields=["status", "error", "updated_at"])
        ingest.start_import(src)
        return Response(_source_json(src))

    def delete(self, request, pk):
        src = self._get(request, pk)
        audit(request, "ai.knowledge_source_deleted", target=src.name)
        src.delete()  # its entries go with it
        return Response(status=204)


class KnowledgeSearchView(APIView):
    """GET ?q=: what the AI would find for this question (free: no AI credit used)."""

    def get(self, request):
        ws = get_membership(request).workspace
        q = str(request.query_params.get("q") or "").strip()[:300]
        if not q:
            return Response([])
        return Response([{k: r[k] for k in ("id", "kind", "title", "content", "source", "source_kind", "score", "match")}
                         for r in search.search(ws, q, limit=5)])


# ------------------------------------------------------------------ AI actions
class SuggestView(AIThrottled):
    def post(self, request):
        conv = _conversation(request, request.data.get("conversation_id"))
        require_feature(conv.workspace, F_AI)
        return _ai_call(ai.suggest_reply, conv, str(request.data.get("instruction") or "")[:300])


class RewriteView(AIThrottled):
    def post(self, request):
        ws = get_membership(request).workspace
        require_feature(ws, F_AI)
        text, mode = str(request.data.get("text") or "").strip(), request.data.get("mode")
        if not text or mode not in ai.REWRITE_MODES:
            return Response({"detail": "Write a message first, then pick how to rewrite it."}, status=400)
        return _ai_call(lambda: {"text": ai.rewrite(ws, text, mode)})


class SummaryView(AIThrottled):
    def post(self, request):
        conv = _conversation(request, request.data.get("conversation_id"))
        require_feature(conv.workspace, F_AI)
        return _ai_call(ai.summarize, conv)


class CaptionView(AIThrottled):
    def post(self, request):
        ws = get_membership(request).workspace
        require_feature(ws, F_AI)
        brief = str(request.data.get("brief") or "").strip()
        if len(brief) < 5:
            return Response({"detail": "Describe the post in a few words first."}, status=400)
        platforms = request.data.get("platforms") or ["facebook"]
        if not isinstance(platforms, list):
            platforms = ["facebook"]
        return _ai_call(ai.captions, ws, brief, [str(p) for p in platforms][:4],
                        tone=str(request.data.get("tone") or "friendly")[:20],
                        language=str(request.data.get("language") or "english")[:20])


class PublishFillView(AIThrottled):
    """POST {media_id?, brief?, platforms, language, tone}: titles, descriptions, tags and captions for every platform,
    written from the video itself (what's said and shown) plus the business's facts."""

    def post(self, request):
        from publishing.models import MediaAsset
        ws = get_membership(request).workspace
        require_feature(ws, F_AI)
        asset = None
        if request.data.get("media_id"):
            asset = MediaAsset.objects.filter(workspace=ws, id=request.data["media_id"]).first()
            if asset is None:
                return Response({"detail": "Unknown media."}, status=400)
        platforms = request.data.get("platforms") or ["facebook"]
        if not isinstance(platforms, list):
            platforms = ["facebook"]
        return _ai_call(ai.publish_fill, ws, asset, str(request.data.get("brief") or "")[:2000], [str(p) for p in platforms][:4],
                        language=str(request.data.get("language") or "english")[:20],
                        tone=str(request.data.get("tone") or "friendly")[:20])


class PlaygroundView(AIThrottled):
    def post(self, request):
        ws = get_membership(request).workspace
        require_feature(ws, F_AI)
        message = str(request.data.get("message") or "").strip()
        if not message:
            return Response({"detail": "Type a customer message to test."}, status=400)
        return _ai_call(ai.playground, ws, message)


# ------------------------------------------------------------------ rules
class RuleIn(serializers.ModelSerializer):
    channel_id = serializers.UUIDField(required=False, allow_null=True)
    add_tag_id = serializers.IntegerField(required=False, allow_null=True)
    assign_to_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = Rule
        fields = ["name", "enabled", "trigger", "channel_id", "keywords", "match", "post_id", "reply_text", "use_ai",
                  "public_reply_text", "add_tag_id", "assign_to_id"]

    def validate_keywords(self, value):
        if not isinstance(value, list) or len(value) > 50:
            raise serializers.ValidationError("Up to 50 keywords.")
        return [str(k).strip()[:60] for k in value if str(k).strip()]

    def validate(self, data):
        ws = self.context["workspace"]
        get = lambda k: data.get(k, getattr(self.instance, k, None))  # noqa: E731
        trigger = get("trigger")
        channel_id = data.get("channel_id", self.instance.channel_id if self.instance else None)
        if channel_id:
            ch = ws.channels.filter(id=channel_id).first()
            if not ch:
                raise serializers.ValidationError({"channel_id": "Unknown channel."})
            if trigger == Rule.COMMENT and (ch.provider not in ("messenger", "instagram") or ch.is_demo):
                raise serializers.ValidationError({"channel_id": "Comment automations need a real Messenger (Facebook Page) or Instagram channel."})
        if trigger == Rule.COMMENT and not channel_id:
            raise serializers.ValidationError({"channel_id": "Pick the Facebook Page or Instagram account."})
        if trigger == Rule.KEYWORD and not get("keywords"):
            raise serializers.ValidationError({"keywords": "Add at least one keyword."})
        if not (get("reply_text") or "").strip() and not get("use_ai") and not (trigger == Rule.KEYWORD and (
                data.get("add_tag_id") or data.get("assign_to_id"))):
            raise serializers.ValidationError({"reply_text": "Write the reply (or let AI answer)."})
        if data.get("add_tag_id") and not Tag.objects.filter(workspace=ws, id=data["add_tag_id"]).exists():
            raise serializers.ValidationError({"add_tag_id": "Unknown tag."})
        if data.get("assign_to_id") and not ws.memberships.filter(user_id=data["assign_to_id"]).exists():
            raise serializers.ValidationError({"assign_to_id": "Not a member of this workspace."})
        if get("use_ai") and not ws.has_feature(F_AI):
            raise serializers.ValidationError({"use_ai": "AI answers aren't included in your plan."})
        return data


def _rule_json(r):
    return {
        "id": str(r.id), "name": r.name, "enabled": r.enabled, "trigger": r.trigger,
        "channel": {"id": str(r.channel_id), "provider": r.channel.provider, "name": r.channel.name} if r.channel_id else None,
        "keywords": r.keywords, "match": r.match, "post_id": r.post_id, "reply_text": r.reply_text, "use_ai": r.use_ai,
        "public_reply_text": r.public_reply_text, "add_tag_id": r.add_tag_id, "assign_to_id": r.assign_to_id,
        "run_count": r.run_count, "last_run_at": r.last_run_at, "last_error": r.last_error, "created_at": r.created_at,
    }


class RulesView(APIView):
    def get(self, request):
        ws = get_membership(request).workspace
        return Response([_rule_json(r) for r in Rule.objects.filter(workspace=ws).select_related("channel")])

    def post(self, request):
        m = require(request, "manage_automations")
        require_feature(m.workspace, F_AUTOMATIONS)
        if Rule.objects.filter(workspace=m.workspace).count() >= MAX_RULES:
            return Response({"detail": f"Up to {MAX_RULES} automations per workspace."}, status=400)
        ser = RuleIn(data=request.data, context={"workspace": m.workspace})
        ser.is_valid(raise_exception=True)
        rule = ser.save(workspace=m.workspace)
        audit(request, "automation.created", target=rule.name, meta={"trigger": rule.trigger})
        return Response(_rule_json(rule), status=201)


class RuleDetailView(APIView):
    def _get(self, request, pk):
        m = require(request, "manage_automations")
        return m, get_object_or_404(Rule, workspace=m.workspace, pk=pk)

    def put(self, request, pk):
        m, rule = self._get(request, pk)
        require_feature(m.workspace, F_AUTOMATIONS)
        ser = RuleIn(rule, data=request.data, partial=True, context={"workspace": m.workspace})
        ser.is_valid(raise_exception=True)
        rule = ser.save()
        audit(request, "automation.updated", target=rule.name)
        return Response(_rule_json(rule))

    def delete(self, request, pk):
        _, rule = self._get(request, pk)
        audit(request, "automation.deleted", target=rule.name)
        rule.delete()
        return Response(status=204)


# ------------------------------------------------------------------ AI staff report
class ReportView(APIView):
    """GET ai/report/?hours=12: what the AI staff did ("While you were away")."""

    def get(self, request):
        from datetime import timedelta

        from django.utils import timezone

        from . import sales
        ws = get_membership(request).workspace
        try:
            hours = max(1, min(int(request.query_params.get("hours", 24)), 24 * 31))
        except ValueError:
            hours = 24
        return Response(sales.stats(ws, timezone.now() - timedelta(hours=hours)))
