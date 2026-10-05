from django.urls import path

from . import views

urlpatterns = [
    path("developers/api-keys/", views.ApiKeysView.as_view()),
    path("developers/api-keys/<uuid:pk>/", views.ApiKeyDetailView.as_view()),
    path("developers/webhooks/", views.WebhooksView.as_view()),
    path("developers/webhooks/<uuid:pk>/", views.WebhookDetailView.as_view()),
    path("developers/webhooks/<uuid:pk>/test/", views.WebhookTestView.as_view()),
    path("developers/webhooks/<uuid:pk>/deliveries/", views.WebhookDeliveriesView.as_view()),
    path("workspace/brand/", views.BrandView.as_view()),
]
