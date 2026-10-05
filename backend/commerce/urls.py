from django.urls import path

from . import views

urlpatterns = [
    path("shop/settings/", views.ShopSettingsView.as_view()),
    path("shop/couriers/<str:courier>/<str:what>/", views.CourierLookupView.as_view()),
    path("products/", views.ProductsView.as_view()),
    path("products/image/", views.ProductImageView.as_view()),
    path("products/<int:pk>/", views.ProductDetailView.as_view()),
    path("customers/", views.CustomersView.as_view()),
    path("customers/<uuid:pk>/", views.CustomerDetailView.as_view()),
    path("customers/<uuid:pk>/merge/", views.CustomerMergeView.as_view()),
    path("conversations/<uuid:conversation_id>/customer/", views.ConversationCustomerView.as_view()),
    path("orders/", views.OrdersView.as_view()),
    path("orders/stats/", views.OrderStatsView.as_view()),
    path("orders/<uuid:pk>/", views.OrderDetailView.as_view()),
    path("orders/<uuid:pk>/<str:action>/", views.OrderActionView.as_view()),
    path("payment-checks/", views.PaymentChecksView.as_view()),
    path("payment-checks/<int:pk>/<str:action>/", views.PaymentCheckActionView.as_view()),
    path("bookings/", views.BookingsView.as_view()),
    path("bookings/<uuid:pk>/", views.BookingDetailView.as_view()),
    path("pay/<uuid:link_id>/", views.PublicPayView.as_view()),
    path("pay/<uuid:link_id>/start/<str:gateway>/", views.PublicPayStartView.as_view()),
    path("pay/<uuid:link_id>/return/<str:gateway>/", views.pay_return),
    path("pay/<uuid:link_id>/return/<str:gateway>/failed/", views.pay_return, {"failed": True}),
]
