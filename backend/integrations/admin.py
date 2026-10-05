from django.contrib import admin

from .models import ChannelAccount


@admin.register(ChannelAccount)
class ChannelAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "workspace", "status", "is_demo", "last_synced_at")
    list_filter = ("provider", "status", "is_demo")
    exclude = ("credentials",)
