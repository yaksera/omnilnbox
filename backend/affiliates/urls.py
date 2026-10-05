from django.urls import path

from . import views

urlpatterns = [
    # public
    path("affiliates/program/", views.ProgramView.as_view()),
    path("affiliates/code/<str:code>/", views.CodeCheckView.as_view()),
    path("affiliates/click/", views.ClickView.as_view()),
    # the signed-in affiliate
    path("affiliates/me/", views.MeView.as_view()),
    path("affiliates/payouts/", views.PayoutRequestView.as_view()),
    # workspace owner: promo code on the Billing page
    path("billing/promo-code/", views.RedeemView.as_view()),
    # platform admin
    path("platform/affiliates/", views.AdminAffiliatesView.as_view()),
    path("platform/affiliates/<int:affiliate_id>/", views.AdminAffiliateDetailView.as_view()),
    path("platform/affiliate-payouts/", views.AdminPayoutsView.as_view()),
    path("platform/affiliate-payouts/<int:payout_id>/", views.AdminPayoutDetailView.as_view()),
]
