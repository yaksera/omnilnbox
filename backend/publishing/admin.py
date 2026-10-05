from django.contrib import admin

from .models import MediaAsset, Post, PostTarget, SocialAccount


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "platform", "workspace", "status", "created_at")
    list_filter = ("platform", "status")
    exclude = ("credentials",)


class TargetInline(admin.TabularInline):
    model = PostTarget
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "workspace", "status", "scheduled_at", "published_at")
    list_filter = ("status",)
    inlines = [TargetInline]


admin.site.register(MediaAsset)
