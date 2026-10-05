from django.urls import path

from . import views

urlpatterns = [
    path("ai/settings/", views.SettingsView.as_view()),
    path("ai/knowledge/", views.KnowledgeView.as_view()),
    path("ai/knowledge/<int:pk>/", views.KnowledgeDetailView.as_view()),
    path("ai/knowledge/search/", views.KnowledgeSearchView.as_view()),
    path("ai/knowledge/sources/", views.SourcesView.as_view()),
    path("ai/knowledge/sources/upload/", views.SourceUploadView.as_view()),
    path("ai/knowledge/sources/url/", views.SourceUrlView.as_view()),
    path("ai/knowledge/sources/<int:pk>/", views.SourceDetailView.as_view()),
    path("ai/suggest/", views.SuggestView.as_view()),
    path("ai/rewrite/", views.RewriteView.as_view()),
    path("ai/summary/", views.SummaryView.as_view()),
    path("ai/caption/", views.CaptionView.as_view()),
    path("ai/publish-fill/", views.PublishFillView.as_view()),
    path("ai/playground/", views.PlaygroundView.as_view()),
    path("ai/report/", views.ReportView.as_view()),
    path("automations/rules/", views.RulesView.as_view()),
    path("automations/rules/<uuid:pk>/", views.RuleDetailView.as_view()),
]
