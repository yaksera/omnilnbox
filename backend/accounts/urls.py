from django.urls import path

from . import views

urlpatterns = [
    path("auth/password/forgot/", views.ForgotPasswordView.as_view()),
    path("auth/password/reset/", views.ResetPasswordView.as_view()),
    path("auth/email/send-verification/", views.SendVerificationView.as_view()),
    path("auth/email/verify/", views.VerifyEmailView.as_view()),
    path("auth/logout-all/", views.LogoutAllView.as_view()),
    path("auth/2fa/setup/", views.TwoFactorSetupView.as_view()),
    path("auth/2fa/enable/", views.TwoFactorEnableView.as_view()),
    path("auth/2fa/disable/", views.TwoFactorDisableView.as_view()),
    path("auth/2fa/login/", views.TwoFactorLoginView.as_view()),
    path("notifications/push/key/", views.PushKeyView.as_view()),
    path("notifications/push/subscribe/", views.PushSubscribeView.as_view()),
    path("notifications/push/test/", views.PushTestView.as_view()),
    path("notifications/prefs/", views.NotificationPrefsView.as_view()),
    path("audit-log/", views.AuditLogView.as_view()),
    path("onboarding/", views.OnboardingView.as_view()),
]
