from django.contrib import admin

from .models import Payment, SalesLead


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("workspace", "plan", "cycle", "currency", "amount", "gateway", "status", "created_at", "paid_at")
    list_filter = ("status", "gateway", "plan")
    search_fields = ("workspace__name", "reference", "gateway_txn_id")
    readonly_fields = ("raw",)


@admin.register(SalesLead)
class SalesLeadAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "company", "created_at", "handled")
    list_filter = ("handled",)
