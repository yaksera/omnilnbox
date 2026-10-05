from django.contrib import admin, messages

from . import services
from .models import Affiliate, Click, Commission, Payout, Referral


@admin.register(Affiliate)
class AffiliateAdmin(admin.ModelAdmin):
    list_display = ("code", "user", "status", "commission_rate", "payout_method", "created_at", "approved_at")
    list_filter = ("status", "payout_method")
    search_fields = ("code", "user__email", "user__first_name")
    exclude = ("payout_details",)  # encrypted; edited by the affiliate in the app


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("workspace", "affiliate", "source", "created_at")
    list_filter = ("source",)
    search_fields = ("workspace__name", "affiliate__code")
    raw_id_fields = ("workspace", "affiliate")


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ("affiliate", "payment", "currency", "amount", "status", "available_at", "payout", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("affiliate__code", "payment__workspace__name")
    raw_id_fields = ("affiliate", "referral", "payment", "payout")
    actions = ["void_selected"]

    @admin.action(description="Void selected commissions (e.g. the customer was refunded)")
    def void_selected(self, request, queryset):
        done = skipped = 0
        for c in queryset:
            try:
                services.void_commission(c, "Voided by admin")
                done += 1
            except services.AffiliateError:
                skipped += 1
        self.message_user(request, f"Voided {done}. Skipped {skipped} (already paid or in a payout request).",
                          messages.WARNING if skipped else messages.SUCCESS)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("affiliate", "currency", "amount", "method", "status", "reference", "requested_at", "processed_at")
    list_filter = ("status", "currency", "method")
    search_fields = ("affiliate__code", "reference")
    exclude = ("details",)


@admin.register(Click)
class ClickAdmin(admin.ModelAdmin):
    list_display = ("affiliate", "landing", "referrer", "created_at")
    search_fields = ("affiliate__code",)
