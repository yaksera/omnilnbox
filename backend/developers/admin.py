from django.contrib import admin

from .models import ApiKey, WebhookEndpoint

admin.site.register(WebhookEndpoint)


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "prefix", "created_at", "last_used_at", "revoked_at")
    readonly_fields = ("key_hash",)
