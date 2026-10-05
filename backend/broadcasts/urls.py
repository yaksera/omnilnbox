from django.urls import path

from . import views

urlpatterns = [
    path("broadcasts/", views.BroadcastsView.as_view()),
    path("broadcasts/audience/", views.AudienceView.as_view()),
    path("broadcasts/templates/", views.TemplatesView.as_view()),
    path("broadcasts/<uuid:pk>/", views.BroadcastDetailView.as_view()),
    path("broadcasts/<uuid:pk>/<str:action>/", views.BroadcastActionView.as_view()),
]
