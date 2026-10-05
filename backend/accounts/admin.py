from django.contrib import admin

from .models import AuditLog, Profile, PushSubscription


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "workspace", "actor_label", "action", "target", "ip")
    list_filter = ("action",)
    search_fields = ("actor_label", "target")


admin.site.register(Profile)
admin.site.register(PushSubscription)
