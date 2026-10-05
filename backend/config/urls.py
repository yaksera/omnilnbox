from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from django.conf import settings

from core.views import (
    InviteAcceptView, InviteRevokeView, LoginView, LogoutView, MemberView, MeView, RefreshView, RegisterView, TeamView,
    WorkspaceView,
)
from billing.views import (
    BillingView, CheckoutView, ContactSalesView, PlansView, payment_return, stripe_webhook,
)
from core import platform
from integrations import meta_connect
from inbox.views import AttachmentUploadView, EventsView, attachment_file
from inbox.views import (
    AnalyticsView, CannedReplyViewSet, ContactViewSet, ConversationViewSet, ExportView, StatsView, TagViewSet,
)
from integrations.views import ChannelViewSet, MicrosoftOAuthCallback, ProvidersView, webhook
from integrations.widget import WidgetConfigView, WidgetMessagesView, WidgetSessionView, WidgetSiteView, WidgetUploadView

router = DefaultRouter()
router.register("channels", ChannelViewSet, basename="channel")
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("contacts", ContactViewSet, basename="contact")
router.register("tags", TagViewSet, basename="tag")
router.register("canned-replies", CannedReplyViewSet, basename="canned")

api = [
    path("auth/register/", RegisterView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("auth/refresh/", RefreshView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("auth/me/", MeView.as_view()),
    path("workspace/", WorkspaceView.as_view()),
    path("team/", TeamView.as_view()),
    path("team/members/<int:user_id>/", MemberView.as_view()),
    path("team/invites/<uuid:invite_id>/", InviteRevokeView.as_view()),
    path("invites/<str:token>/", InviteAcceptView.as_view()),
    path("providers/", ProvidersView.as_view()),
    path("plans/", PlansView.as_view()),
    path("billing/", BillingView.as_view()),
    path("billing/checkout/", CheckoutView.as_view()),
    path("billing/return/<str:gateway_key>/<uuid:payment_id>/", payment_return),
    path("billing/return/<str:gateway_key>/<uuid:payment_id>/failed/", payment_return, {"failed": True}),
    path("billing/webhook/stripe/", stripe_webhook),
    path("contact-sales/", ContactSalesView.as_view()),
    path("stats/", StatsView.as_view()),
    path("events/", EventsView.as_view()),
    path("platform/overview/", platform.OverviewView.as_view()),
    path("platform/insights/", platform.InsightsView.as_view()),
    path("platform/workspaces/", platform.WorkspacesView.as_view()),
    path("platform/workspaces/<uuid:ws_id>/", platform.WorkspaceDetailView.as_view()),
    path("attachments/", AttachmentUploadView.as_view()),
    path("attachments/<uuid:att_id>/<str:token>/", attachment_file),
    path("analytics/", AnalyticsView.as_view()),
    path("analytics/export.csv", ExportView.as_view()),
    path("webhooks/meta/", meta_connect.meta_webhook),
    path("webhooks/<uuid:channel_id>/", webhook, name="webhook"),
    path("meta/config/", meta_connect.MetaConfigView.as_view()),
    path("meta/whatsapp/", meta_connect.WhatsAppConnectView.as_view()),
    path("meta/pages/", meta_connect.PagesListView.as_view()),
    path("meta/pages/connect/", meta_connect.PagesConnectView.as_view()),
    path("widget/site/", WidgetSiteView.as_view()),
    path("widget/<uuid:channel_id>/", WidgetConfigView.as_view()),
    path("widget/<uuid:channel_id>/session/", WidgetSessionView.as_view()),
    path("widget/<uuid:channel_id>/messages/", WidgetMessagesView.as_view()),
    path("widget/<uuid:channel_id>/upload/", WidgetUploadView.as_view()),
    path("oauth/microsoft/callback/", MicrosoftOAuthCallback.as_view()),
    path("publishing/", include("publishing.urls")),
    path("", include("automations.urls")),
    path("", include("accounts.urls")),
    path("", include("commerce.urls")),
    path("", include("broadcasts.urls")),
    path("", include("developers.urls")),
    path("", include("affiliates.urls")),
    path("", include(router.urls)),
]

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", include(api)),
    path("health/", lambda r: JsonResponse({"ok": True})),
]
