import csv
from datetime import timedelta

from django.db.models import Avg, Count, Exists, F, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.plans import F_ANALYTICS, F_CANNED, F_EXPORT, F_NOTES, F_TAGS
from core.permissions import require, require_feature
from core.tenancy import WorkspaceScopedMixin, get_membership, get_workspace

from .models import Attachment, CannedReply, Contact, Conversation, CsatResponse, Message, Tag
from .serializers import (
    CannedReplySerializer, ContactSerializer, ConversationSerializer, MessageSerializer, SendMessageSerializer,
    TagSerializer,
)
from .services import add_note, send_csat_survey, send_reply


def visible_conversations(request, qs):
    """Agents may be limited to their own + unassigned conversations (Business plan setting)."""
    m = get_membership(request)
    if m.role == "agent" and not m.workspace.agents_see_all and m.workspace.has_feature("agent_visibility"):
        qs = qs.filter(Q(assigned_to=request.user) | Q(assigned_to__isnull=True))
    return qs


class ConversationViewSet(WorkspaceScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/conversations/?provider=whatsapp&channel=<id>&status=open&unread=1&q=text&assigned=me
    GET  /api/conversations/<id>/
    PATCH /api/conversations/<id>/  {status, assigned_to_id}
    GET  /api/conversations/<id>/messages/
    POST /api/conversations/<id>/messages/ {text}
    POST /api/conversations/<id>/read/
    """

    queryset = Conversation.objects.select_related("contact", "channel", "assigned_to").prefetch_related("tags")
    serializer_class = ConversationSerializer

    def get_queryset(self):
        qs = visible_conversations(self.request, super().get_queryset())
        p = self.request.query_params
        if p.get("tag"):
            qs = qs.filter(tags__id=p["tag"]) if p["tag"].isdigit() else qs.none()
        if p.get("provider"):
            qs = qs.filter(channel__provider__in=p["provider"].split(","))
        if p.get("category") == "email":
            qs = qs.filter(channel__provider__in=["gmail", "outlook", "zoho", "imap"])
        if p.get("channel"):
            qs = qs.filter(channel_id=p["channel"])
        if p.get("status") and p["status"] != "all":
            qs = qs.filter(status=p["status"])
        if p.get("unread") in ("1", "true"):
            qs = qs.filter(unread_count__gt=0)
        # Mobile inbox tabs: "message" (DMs, chats, email) or "comment" (public post comments)
        if p.get("kind") == "comment":
            qs = qs.filter(meta__kind="comment")
        elif p.get("kind") == "message":
            # (not .exclude(): rows without a "kind" key would be dropped too)
            qs = qs.filter(Q(meta__kind__isnull=True) | ~Q(meta__kind="comment"))
        if p.get("ai") == "handoff":  # the AI bot handed these to a human
            qs = qs.filter(meta__bot_paused=True).exclude(status=Conversation.STATUS_CLOSED)
        if p.get("assigned") == "me":
            qs = qs.filter(assigned_to=self.request.user)
        elif p.get("assigned") == "unassigned":
            qs = qs.filter(assigned_to__isnull=True)
        if p.get("q"):
            q = p["q"][:100]
            # EXISTS subquery instead of JOIN + DISTINCT over every message row
            has_text = Message.objects.filter(conversation=OuterRef("pk"), text__icontains=q)
            qs = qs.filter(
                Q(contact__name__icontains=q) | Q(contact__handle__icontains=q) | Q(subject__icontains=q)
                | Exists(has_text)
            )
        # who sent the last message, for "You: ..." in the list (one subquery, no extra queries per row)
        last_dir = Message.objects.filter(conversation=OuterRef("pk"), is_note=False).order_by("-sent_at").values("direction")[:1]
        return qs.annotate(last_direction=Subquery(last_dir)).order_by("-last_message_at")

    def get_throttles(self):
        if self.action == "messages" and self.request.method == "POST":
            self.throttle_scope = "send"  # cap outgoing messages per user (anti-spam)
        return super().get_throttles()

    def perform_update(self, serializer):
        m = get_membership(self.request)
        assigned = serializer.validated_data.pop("assigned_to_id", "unset")
        tag_ids = serializer.validated_data.pop("tag_ids", None)
        if assigned != "unset":
            current = serializer.instance.assigned_to_id
            taking_or_releasing_own = assigned == self.request.user.id or (
                assigned is None and current in (None, self.request.user.id))
            if not taking_or_releasing_own:
                require(self.request, "assign_others")  # agents can only take or release their own
        if tag_ids is not None:
            require_feature(m.workspace, F_TAGS)
        was_closed = serializer.instance.status == Conversation.STATUS_CLOSED
        conv = serializer.save()
        if conv.status == Conversation.STATUS_CLOSED and not was_closed:
            if conv.meta.get("bot_paused"):
                # Done with this customer: the AI assistant may answer them again next time.
                conv.meta = {k: v for k, v in conv.meta.items() if not k.startswith("bot_")}
                conv.save(update_fields=["meta"])
            from developers.events import emit
            emit("conversation.closed", conv.workspace_id, {"id": str(conv.id), "channel": conv.channel.provider,
                                                           "contact": conv.contact.name, "closed_by": self.request.user.email})
            send_csat_survey(conv, self.request.user)
        if assigned != "unset":
            conv.assigned_to_id = assigned
            conv.save(update_fields=["assigned_to"])
        if tag_ids is not None:
            conv.tags.set(Tag.objects.filter(workspace=m.workspace, id__in=tag_ids))

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        conv = self.get_object()
        if request.method == "GET":
            msgs = conv.messages.all()
            days = conv.workspace.plan_info["history_days"]
            if days:
                msgs = msgs.filter(sent_at__gte=timezone.now() - timedelta(days=days))
            after = parse_datetime(request.query_params.get("after") or "")
            if after:
                msgs = msgs.filter(created_at__gt=after)  # only rows added since the client's last fetch
            return Response(MessageSerializer(msgs.prefetch_related("files"), many=True).data)
        ser = SendMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if ser.validated_data.get("note"):
            require_feature(conv.workspace, F_NOTES)
            return Response(MessageSerializer(add_note(conv, ser.validated_data["text"], request.user)).data,
                            status=status.HTTP_201_CREATED)
        files = []
        ids = ser.validated_data.get("attachment_ids") or []
        if ids:
            from integrations.providers import get_provider_class
            cls = get_provider_class(conv.channel.provider)
            if not (cls and cls.can_send_media) and not conv.channel.is_demo:
                return Response({"detail": f"{conv.channel.get_provider_display()} doesn't support sending files yet."},
                                status=400)
            files = list(Attachment.objects.filter(id__in=ids, workspace=conv.workspace, message__isnull=True,
                                                   status=Attachment.READY))
            if len(files) != len(set(ids)):
                return Response({"attachment_ids": ["A file is missing or was already sent. Attach it again."]}, status=400)
            files.sort(key=lambda f: ids.index(f.id))
        msg = send_reply(conv, ser.validated_data["text"], user=request.user, files=files)
        if msg.status == Message.STATUS_SENT and not conv.meta.get("bot_paused"):
            # A person took over: the AI bot stays quiet here until it's resumed or the conversation is closed.
            conv.meta = {**conv.meta, "bot_paused": True, "bot_pause_reason": "agent"}
            conv.save(update_fields=["meta"])
        code = status.HTTP_201_CREATED if msg.status != Message.STATUS_FAILED else status.HTTP_502_BAD_GATEWAY
        return Response(MessageSerializer(msg).data, status=code)

    @action(detail=True, methods=["post"], url_path="private-reply")
    def private_reply(self, request, pk=None):
        """Comment threads: send the commenter a private message (Messenger / Instagram DM)."""
        from integrations.providers import ProviderError, get_provider
        conv = self.get_object()
        text = str(request.data.get("text") or "").strip()
        if conv.meta.get("kind") != "comment" or not text:
            return Response({"detail": "Write a message for a comment conversation."}, status=400)
        provider = get_provider(conv.channel)
        if not hasattr(provider, "private_reply"):
            return Response({"detail": "Private replies aren't available for this channel."}, status=400)
        try:
            ext = provider.private_reply(conv, text)
            status_, error = Message.STATUS_SENT, ""
        except ProviderError as exc:
            ext, status_, error = "", Message.STATUS_FAILED, str(exc)[:2000]
        msg = Message.objects.create(conversation=conv, direction=Message.DIRECTION_OUT, external_id=ext or "",
                                     sender_name=request.user.get_full_name() or request.user.email, sent_by=request.user,
                                     text=f"🔒 Private message: {text}", status=status_, error=error, sent_at=timezone.now())
        return Response(MessageSerializer(msg).data, status=201 if status_ == Message.STATUS_SENT else 502)

    @action(detail=True, methods=["post"])
    def bot(self, request, pk=None):
        """POST {paused: true|false}: stop or resume the AI assistant in this conversation."""
        conv = self.get_object()
        if request.data.get("paused") in (True, "true", 1, "1"):
            conv.meta = {**conv.meta, "bot_paused": True, "bot_pause_reason": "manual"}
        else:
            conv.meta = {k: v for k, v in conv.meta.items() if not k.startswith("bot_")}
        conv.save(update_fields=["meta"])
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        conv = self.get_object()
        conv.unread_count = 0
        conv.save(update_fields=["unread_count"])
        return Response({"ok": True})


class ContactViewSet(WorkspaceScopedMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                     mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer


class StatsView(APIView):
    """Counts used by the sidebar badges and dashboard."""

    def get(self, request):
        ws = get_workspace(request)
        convs = visible_conversations(request, Conversation.objects.filter(workspace=ws))
        by_provider = (
            convs.values("channel__provider")
            .annotate(conversations=Count("id"), unread=Sum("unread_count"))
            .order_by()
        )
        # one aggregate query instead of five separate COUNTs
        totals = convs.aggregate(
            total=Count("id"),
            open=Count("id", filter=Q(status=Conversation.STATUS_OPEN)),
            unread_convs=Count("id", filter=Q(unread_count__gt=0)),
            unread_msgs=Sum("unread_count"),
            mine=Count("id", filter=Q(assigned_to=request.user, status=Conversation.STATUS_OPEN)),
            unread_comments=Count("id", filter=Q(unread_count__gt=0, meta__kind="comment")),
            handoff=Count("id", filter=Q(meta__bot_paused=True) & ~Q(status=Conversation.STATUS_CLOSED)),
        )
        return Response({
            "total_conversations": totals["total"],
            "open": totals["open"],
            "unread_conversations": totals["unread_convs"],
            "unread_messages": totals["unread_msgs"] or 0,
            "assigned_to_me": totals["mine"],
            "unread_by_kind": {"message": totals["unread_convs"] - totals["unread_comments"], "comment": totals["unread_comments"]},
            "ai_handoff": totals["handoff"],
            "by_provider": {
                row["channel__provider"]: {"conversations": row["conversations"], "unread": row["unread"] or 0}
                for row in by_provider
            },
        })


class TagViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    pagination_class = None

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            require(request, "manage_tags")
            require_feature(get_workspace(request), F_TAGS)

    def perform_create(self, serializer):
        serializer.save(workspace=self.get_workspace())


class CannedReplyViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = CannedReply.objects.all()
    serializer_class = CannedReplySerializer
    pagination_class = None

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            require(request, "manage_canned")
            require_feature(get_workspace(request), F_CANNED)

    def perform_create(self, serializer):
        serializer.save(workspace=self.get_workspace(), created_by=self.request.user)


def _window(request):
    try:
        days = max(1, min(int(request.query_params.get("days", 14)), 90))
    except ValueError:
        days = 14
    return days, timezone.now() - timedelta(days=days)


class AnalyticsView(APIView):
    """Team performance for the last N days (Pro and higher)."""

    def get(self, request):
        m = require(request, "view_analytics")
        ws = m.workspace
        require_feature(ws, F_ANALYTICS)
        days, since = _window(request)
        msgs = Message.objects.filter(conversation__workspace=ws, sent_at__gte=since, is_note=False)
        convs = Conversation.objects.filter(workspace=ws, created_at__gte=since)

        daily = {}
        for row in (msgs.annotate(day=TruncDate("sent_at")).values("day", "direction")
                    .annotate(n=Count("id")).order_by("day")):
            d = daily.setdefault(str(row["day"]), {"date": str(row["day"]), "in": 0, "out": 0})
            d[row["direction"]] = row["n"]
        series = []
        for i in range(days, -1, -1):
            day = str((timezone.now() - timedelta(days=i)).date())
            series.append(daily.get(day, {"date": day, "in": 0, "out": 0}))

        # First response time = first agent reply - customer's first message (not import time)
        pairs = (Conversation.objects.filter(workspace=ws, first_response_at__gte=since)
                 .annotate(first_in=Min("messages__sent_at", filter=Q(messages__direction="in", messages__is_note=False)))
                 .values_list("first_response_at", "first_in"))
        deltas = [(r - i).total_seconds() for r, i in pairs if i is not None and r >= i]
        frt_minutes = round(sum(deltas) / len(deltas) / 60, 1) if deltas else None
        by_channel = list(msgs.values(provider=F("conversation__channel__provider"))
                          .annotate(incoming=Count("id", filter=Q(direction="in")),
                                    outgoing=Count("id", filter=Q(direction="out"))).order_by("-incoming"))
        by_agent = list(msgs.filter(direction="out", sent_by__isnull=False)
                        .values("sent_by_id", "sent_by__email", "sent_by__first_name", "sent_by__last_name")
                        .annotate(replies=Count("id")).order_by("-replies")[:20])
        # Response-time target (SLA): share of first replies within the workspace's target
        target = ws.sla_minutes * 60
        within = sum(1 for d in deltas if d <= target) if target else 0
        csat_qs = CsatResponse.objects.filter(workspace=ws, created_at__gte=since)
        csat = csat_qs.aggregate(avg=Avg("score"), n=Count("id"), happy=Count("id", filter=Q(score__gte=4)))
        csat_agents = list(csat_qs.filter(agent__isnull=False).values("agent__email", "agent__first_name", "agent__last_name")
                           .annotate(avg=Avg("score"), n=Count("id")).order_by("-n")[:20])
        return Response({
            "days": days,
            "sla": {"target_minutes": ws.sla_minutes, "met_pct": round(within * 100 / len(deltas)) if (target and deltas) else None,
                    "measured": len(deltas)},
            "csat": {"enabled": ws.csat_enabled, "responses": csat["n"], "avg": round(csat["avg"], 2) if csat["avg"] else None,
                     "happy_pct": round(csat["happy"] * 100 / csat["n"]) if csat["n"] else None,
                     "by_agent": [{"name": (f"{a['agent__first_name']} {a['agent__last_name']}".strip() or a["agent__email"]),
                                   "avg": round(a["avg"], 2), "responses": a["n"]} for a in csat_agents],
                     "recent": [{"score": r.score, "comment": r.comment, "at": r.created_at,
                                 "contact": r.conversation.contact.name} for r in csat_qs.select_related("conversation__contact")[:10]]},
            "totals": {
                "new_conversations": convs.count(),
                "incoming": msgs.filter(direction="in").count(),
                "outgoing": msgs.filter(direction="out").count(),
                "closed": Conversation.objects.filter(workspace=ws, status="closed", last_message_at__gte=since).count(),
                "avg_first_response_minutes": frt_minutes,
            },
            "series": series,
            "by_channel": by_channel,
            "by_agent": [{"name": (f"{a['sent_by__first_name']} {a['sent_by__last_name']}".strip()
                                   or a["sent_by__email"]), "replies": a["replies"]} for a in by_agent],
        })


class ExportView(APIView):
    """CSV export of conversations (Business plan)."""

    def get(self, request):
        m = require(request, "view_analytics")
        require_feature(m.workspace, F_EXPORT)
        from accounts.audit import audit
        audit(request, "export.csv", target=f"{request.query_params.get('days', '30')} days")
        days, since = _window(request)
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="conversations-{days}d.csv"'
        w = csv.writer(resp)
        w.writerow(["id", "channel", "contact", "handle", "status", "assigned_to", "tags", "created_at",
                    "last_message_at", "first_response_at"])
        qs = (Conversation.objects.filter(workspace=m.workspace, last_message_at__gte=since)
              .select_related("channel", "contact", "assigned_to").prefetch_related("tags"))
        for c in qs:
            # Neutralise spreadsheet formula injection in user-controlled cells
            safe = [str(x) if not str(x).startswith(("=", "+", "-", "@")) else "'" + str(x) for x in (
                c.contact.name, c.contact.handle)]
            w.writerow([c.id, c.channel.provider, *safe, c.status, c.assigned_to.email if c.assigned_to else "",
                        ";".join(t.name for t in c.tags.all()), c.created_at, c.last_message_at, c.first_response_at])
        return resp


# ------------------------------------------------------------------ files (photos, voice notes, documents)
class AttachmentUploadView(APIView):
    """POST multipart {file, kind?}: upload a file to send in a conversation (then pass its id when sending)."""

    throttle_scope = "send"

    def post(self, request):
        from . import media
        m = get_membership(request)
        f = request.FILES.get("file")
        if not f:
            return Response({"file": ["Choose a file."]}, status=400)
        if f.size > media.MAX_BYTES:
            return Response({"file": [f"Files can be at most {media.MAX_BYTES // (1024 * 1024)} MB."]}, status=400)
        kind = request.data.get("kind") if request.data.get("kind") in ("voice",) else ""
        att = Attachment.objects.create(workspace=m.workspace, uploaded_by=request.user, kind=kind or "file",
                                        name=(f.name or "file")[:255], mime=(f.content_type or "")[:120])
        media.store_bytes(att, f.read(), f.content_type or "", f.name or "")
        if kind == "voice":
            att.kind = "voice"
            att.save(update_fields=["kind"])
            media.normalize_voice(att)
        return Response(media.as_json(att), status=201)


def attachment_file(request, att_id, token):
    """Serve a stored file for a signed link. Only safe types are shown inline; the rest always download."""
    from django.http import FileResponse, Http404
    from . import media
    if not media.read_token(att_id, token):
        raise Http404
    att = Attachment.objects.filter(id=att_id, status=Attachment.READY).first()
    if att is None or not att.file:
        raise Http404
    inline = att.mime in media.INLINE
    resp = FileResponse(att.file.open("rb"), content_type=att.mime if inline else "application/octet-stream",
                        as_attachment=not inline or request.GET.get("download") == "1", filename=att.name or "file")
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; media-src 'self'; sandbox"
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


class EventsView(APIView):
    """GET /api/events/?v=<version>: waits (up to ~20 s) until something changes in the workspace."""

    def get(self, request):
        from core.realtime import wait
        m = get_membership(request)
        version, changed = wait(m.workspace_id, request.query_params.get("v", ""))
        return Response({"v": version, "changed": changed})
