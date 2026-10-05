from django.contrib import admin

from .models import Contact, Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("contact", "channel", "status", "unread_count", "last_message_at")
    list_filter = ("status", "channel__provider")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "direction", "status", "sent_at")
    list_filter = ("direction", "status")


admin.site.register(Contact)
