from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.ConfigView.as_view()),
    path("accounts/", views.AccountsView.as_view()),
    path("accounts/facebook/", views.ConnectFacebookView.as_view()),
    path("accounts/<uuid:account_id>/", views.AccountDetailView.as_view()),
    path("accounts/<uuid:account_id>/tiktok/", views.TikTokCreatorView.as_view()),
    path("oauth/<str:platform>/start/", views.OAuthStartView.as_view()),
    path("oauth/<str:platform>/callback/", views.oauth_callback),
    path("media/", views.MediaUploadView.as_view()),
    path("files/<str:token>/", views.media_file),
    path("posts/", views.PostsView.as_view()),
    path("posts/<uuid:post_id>/", views.PostDetailView.as_view()),
    path("posts/<uuid:post_id>/retry/", views.RetryView.as_view()),
]
