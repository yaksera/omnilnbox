import logging
from urllib.parse import urlencode
from accounts.audit import audit

from django.conf import settings
from django.core import signing
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import require
from core.tenancy import WorkspaceScopedMixin
from inbox.services import ingest_message

from .models import ChannelAccount
from .providers import PROVIDERS, ProviderError, get_provider
from .providers.demo import seed_demo_workspace
from .serializers import ChannelAccountSerializer
from .sync import sync_channel

logger = logging.getLogger(__name__)
OAUTH_SALT = "omniinbox.oauth"


class ProvidersView(APIView):
    def get(self, request):
        return Response([cls.describe() for cls in PROVIDERS.values()])


def _connect(channel):
    """Verify credentials and run provider setup. Updates channel status."""
    provider = get_provider(channel)
    if getattr(PROVIDERS.get(channel.provider), "uses_oauth", False) and not channel.is_demo \
            and not channel.credentials.get("refresh_token"):
        channel.status = ChannelAccount.STATUS_PENDING
        channel.last_error = ""
        channel.save(update_fields=["status", "last_error"])
        return {"needs_oauth": True}
    try:
        info = provider.verify() or {}
        if info.get("bot_id"):
            channel.state["bot_id"] = str(info["bot_id"])
        info.update(provider.on_connect() or {})
        channel.state["account_info"] = info
        meta_key = {"whatsapp": "phone_number_id", "messenger": "page_id", "instagram": "ig_account_id"}.get(channel.provider)
        if meta_key and channel.credentials.get(meta_key):
            channel.state["meta_id"] = str(channel.credentials[meta_key]).strip()  # routes the shared Meta webhook
        channel.status = ChannelAccount.STATUS_ACTIVE
        channel.last_error = ""
    except ProviderError as exc:
        channel.status = ChannelAccount.STATUS_ERROR
        channel.last_error = str(exc)
        info = {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Connecting %s failed", channel)
        channel.status = ChannelAccount.STATUS_ERROR
        channel.last_error = f"Unexpected error ({type(exc).__name__}). Check the server logs."
        info = {"error": channel.last_error}
    channel.save()
    return info


class ChannelViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = ChannelAccount.objects.all()
    serializer_class = ChannelAccountSerializer
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().annotate(unread_count=Sum("conversations__unread_count"))

    def _require_admin(self):
        require(self.request, "manage_channels")

    def perform_create(self, serializer):
        self._require_admin()
        ws = self.get_workspace()
        real_count = ChannelAccount.objects.filter(workspace=ws, is_demo=False).count()
        if real_count >= ws.channel_limit:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": f"Your {ws.plan_info['name']} plan allows {ws.channel_limit} channels. "
                                             "Upgrade on the Billing page to add more."})
        channel = serializer.save(workspace=ws, created_by=self.request.user)
        _connect(channel)
        audit(self.request, "channel.connected", target=f"{channel.get_provider_display()}: {channel.name}")

    def perform_update(self, serializer):
        self._require_admin()
        channel = serializer.save()
        if not channel.is_demo:
            _connect(channel)
            audit(self.request, "channel.updated", target=f"{channel.get_provider_display()}: {channel.name}")

    def perform_destroy(self, instance):
        self._require_admin()
        audit(self.request, "channel.removed", target=f"{instance.get_provider_display()}: {instance.name}")
        instance.delete()

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        self._require_admin()
        channel = self.get_object()
        info = _connect(channel)
        channel.refresh_from_db()
        return Response({"info": info, "channel": ChannelAccountSerializer(channel).data})

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        channel = self.get_object()
        count = sync_channel(channel)
        channel.refresh_from_db()
        return Response({"new_messages": count, "channel": ChannelAccountSerializer(channel).data})

    @action(detail=True, methods=["post"], url_path="oauth/start")
    def oauth_start(self, request, pk=None):
        self._require_admin()
        channel = self.get_object()
        provider = get_provider(channel)
        if not hasattr(provider, "authorize_url"):
            return Response({"detail": "This channel does not use OAuth."}, status=400)
        state = signing.dumps({"channel": str(channel.id), "user": request.user.id}, salt=OAUTH_SALT)
        try:
            return Response({"url": provider.authorize_url(state)})
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=400)

    @action(detail=False, methods=["post"])
    def demo(self, request):
        """Load demo channels + conversations into the current workspace."""
        self._require_admin()
        created = seed_demo_workspace(self.get_workspace(), request.user)
        return Response({"created": len(created)}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["delete"], url_path="demo/clear")
    def demo_clear(self, request):
        self._require_admin()
        deleted, _ = ChannelAccount.objects.filter(workspace=self.get_workspace(), is_demo=True).delete()
        return Response({"deleted": deleted})


class MicrosoftOAuthCallback(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        target = f"{settings.FRONTEND_URL}/channels"
        if request.GET.get("error"):
            msg = urlencode({"oauth": "error", "message": request.GET.get("error_description", "")[:200]})
            return HttpResponseRedirect(f"{target}?{msg}")
        try:
            data = signing.loads(request.GET.get("state", ""), salt=OAUTH_SALT, max_age=900)
        except signing.BadSignature:
            return HttpResponseRedirect(f"{target}?oauth=error&message=Invalid+state")
        channel = get_object_or_404(ChannelAccount, id=data["channel"])
        try:
            get_provider(channel).exchange_code(request.GET.get("code", ""))
            channel.refresh_from_db()
            _connect(channel)
        except ProviderError as exc:
            channel.mark_error(exc)
            return HttpResponseRedirect(f"{target}?oauth=error&message=Token+exchange+failed")
        return HttpResponseRedirect(f"{target}?oauth=success")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request, channel_id):
    """Public endpoint that platforms call: /api/webhooks/<channel_id>/"""
    channel = ChannelAccount.objects.select_related("workspace").filter(id=channel_id, is_demo=False).first()
    if channel is None or channel.status == ChannelAccount.STATUS_DISABLED:
        return HttpResponse(status=404)
    if channel.workspace.suspended_at and request.method == "POST":
        return JsonResponse({"ok": True, "stored": 0})  # suspended: accept (so platforms don't retry) but ignore
    provider = get_provider(channel)

    if request.method == "GET":
        response = provider.webhook_challenge(request)
        return response or HttpResponse("ok")

    if not provider.validate_webhook(request):
        logger.warning("Rejected webhook with bad signature for channel %s", channel.id)
        return HttpResponse("invalid signature", status=403)
    try:
        items = provider.parse_webhook(request)
    except Exception:  # noqa: BLE001 - never make the platform retry forever
        logger.exception("Failed to parse webhook for %s", channel)
        return JsonResponse({"ok": True, "stored": 0})
    stored = sum(1 for item in items if ingest_message(channel, item))
    if channel.provider in ("messenger", "instagram"):
        try:
            from automations.comments import handle_webhook
            handle_webhook(channel, request.body)  # comment-to-DM automations
        except Exception:  # noqa: BLE001
            logger.exception("Comment automation failed for %s", channel)
    return JsonResponse({"ok": True, "stored": stored})
