from rest_framework import serializers

from core.serializers import UserSerializer

from .models import CannedReply, Contact, Conversation, Message, Tag


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["id", "name", "handle", "avatar_url", "external_id", "notes", "created_at"]
        read_only_fields = ["id", "external_id", "created_at"]


class ChannelMiniSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.CharField()
    name = serializers.CharField()
    is_demo = serializers.BooleanField()
    can_send_media = serializers.SerializerMethodField()

    def get_can_send_media(self, obj):
        from integrations.providers import get_provider_class
        cls = get_provider_class(obj.provider)
        return bool(obj.is_demo or (cls and cls.can_send_media))


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "color"]

    def validate_color(self, value):
        import re
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Use a hex colour like #6366f1.")
        return value


class CannedReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = CannedReply
        fields = ["id", "shortcut", "title", "body", "created_at"]
        read_only_fields = ["id", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    contact = ContactSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)
    channel = ChannelMiniSerializer(read_only=True)
    assigned_to = UserSerializer(read_only=True)
    assigned_to_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    ai = serializers.SerializerMethodField()
    kind = serializers.SerializerMethodField()
    last_direction = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id", "channel", "contact", "subject", "status", "assigned_to", "assigned_to_id", "tags", "tag_ids",
            "unread_count", "last_message_at", "last_message_preview", "first_response_at", "created_at", "ai", "kind",
            "last_direction",
        ]
        read_only_fields = ["id", "subject", "unread_count", "last_message_at", "last_message_preview",
                            "first_response_at", "created_at"]

    def get_last_direction(self, obj):
        """"in" / "out" for the newest message (annotated by the list query; null elsewhere)."""
        return getattr(obj, "last_direction", None)

    def get_kind(self, obj):
        """"message" (DM / email) or "comment" (public comment on a Facebook / Instagram post)."""
        return (obj.meta or {}).get("kind", "message")

    def get_ai(self, obj):
        m = obj.meta or {}
        return {"bot_paused": bool(m.get("bot_paused")), "pause_reason": m.get("bot_pause_reason", ""),
                "handoff_reason": m.get("bot_handoff_reason", ""), "category": m.get("ai_category", ""),
                "sentiment": m.get("ai_sentiment", ""), "summary": m.get("ai_summary")}

    def validate_assigned_to_id(self, value):
        if value is None:
            return value
        ws = self.instance.workspace if self.instance else None
        if ws and not ws.memberships.filter(user_id=value).exists():
            raise serializers.ValidationError("User is not a member of this workspace.")
        return value


class MessageSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()

    def get_attachments(self, obj):
        from .media import message_files
        return message_files(obj)

    class Meta:
        model = Message
        fields = [
            "id", "direction", "is_note", "bot", "sender_name", "text", "html", "attachments",
            "status", "error", "sent_at", "created_at", "sources",
        ]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=10000, trim_whitespace=True, required=False, allow_blank=True, default="")
    note = serializers.BooleanField(required=False, default=False)
    attachment_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=10)

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("attachment_ids"):
            raise serializers.ValidationError({"text": ["Write a message or attach a file."]})
        if attrs.get("note") and attrs.get("attachment_ids"):
            raise serializers.ValidationError({"attachment_ids": ["Files can't be added to internal notes."]})
        return attrs
