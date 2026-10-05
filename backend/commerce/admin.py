from django.contrib import admin

from .models import Customer, Order, OrderItem, PaymentLink, Product, ShopSettings


class ItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "workspace", "status", "payment_status", "total", "created_at")
    list_filter = ("status", "payment_status")
    search_fields = ("number", "recipient_name", "recipient_phone")
    inlines = [ItemInline]


admin.site.register(Product)
admin.site.register(Customer)
admin.site.register(PaymentLink)
admin.site.register(ShopSettings)
