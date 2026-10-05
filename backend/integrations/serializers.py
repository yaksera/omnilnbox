from rest_framework import serializers

from .models import ChannelAccount
from .providers import PROVIDERS

MASK = "••••••••"


class ChannelAccountSerializer(serializers.ModelSerializer):
    credentials = serializers.DictField(required=False, write_only=True)
    credentials_preview = serializers.SerializerMethodField()
    webhook_url = serializers.CharField(read_only=True)
    verify_token = serializers.SerializerMethodField()
    receive_mode = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True, default=0)
    authorized = serializers.SerializerMethodField()
    webhook_public = serializers.SerializerMethodField()

    class Meta:
        model = ChannelAccount
        fields = [
            "id", "provider", "name", "credentials", "credentials_preview", "status", "last_error",
            "last_synced_at", "is_demo", "webhook_url", "verify_token", "receive_mode", "unread_count",
            "authorized", "webhook_public", "created_at",
        ]
        read_only_fields = ["id", "status", "last_error", "last_synced_at", "is_demo", "created_at"]

    def _provider_cls(self, obj):
        return PROVIDERS.get(obj.provider)

    def get_credentials_preview(self, obj):
        cls = self._provider_cls(obj)
        secret_names = {f.name for f in cls.fields if f.secret} if cls else set()
        out = {}
        for key, value in (obj.credentials or {}).items():
            if key in ("access_token", "refresh_token", "expires_at") and cls and cls.uses_oauth:
                continue
            out[key] = MASK if key in secret_names and value else value
        return out

    def get_verify_token(self, obj):
        if obj.provider in ("whatsapp", "messenger", "instagram"):
            return (obj.credentials or {}).get("verify_token") or obj.webhook_secret
        return None

    def get_receive_mode(self, obj):
        from .providers import get_provider
        return get_provider(obj).receive_mode

    def get_webhook_public(self, obj):
        """False when the webhook URL can't be reached by Meta/Telegram/TikTok (localhost or plain http)."""
        from urllib.parse import urlparse
        u = urlparse(obj.webhook_url)
        return u.scheme == "https" and u.hostname not in ("localhost", "127.0.0.1", "0.0.0.0", "::1")

    def get_authorized(self, obj):
        cls = self._provider_cls(obj)
        if cls and cls.uses_oauth and not obj.is_demo:
            return bool((obj.credentials or {}).get("refresh_token"))
        return True

    def validate_provider(self, value):
        if value not in PROVIDERS:
            raise serializers.ValidationError("Unknown provider.")
        return value

    def validate(self, attrs):
        provider_key = attrs.get("provider") or (self.instance.provider if self.instance else None)
        cls = PROVIDERS[provider_key]
        incoming = attrs.get("credentials")
        if incoming is not None:
            existing = dict(self.instance.credentials) if self.instance else {}
            merged = dict(existing)
            allowed = {f.name for f in cls.fields}
            for key, value in incoming.items():
                if key not in allowed:
                    # Only declared fields may be set. This stops clients from injecting
                    # internal values such as OAuth access/refresh tokens.
                    raise serializers.ValidationError({"credentials": {key: "Unknown field."}})
                if value == MASK:
                    continue  # unchanged secret
                if not isinstance(value, (str, int)) or len(str(value)) > 4096:
                    raise serializers.ValidationError({"credentials": {key: "Invalid value."}})
                merged[key] = str(value).strip()
            for f in cls.fields:
                if f.required and not merged.get(f.name):
                    if f.default:
                        merged[f.name] = f.default
                    else:
                        raise serializers.ValidationError({"credentials": {f.name: f"{f.label} is required."}})
                elif not merged.get(f.name) and f.default:
                    merged[f.name] = f.default
            attrs["credentials"] = merged
        elif not self.instance:
            raise serializers.ValidationError({"credentials": "Credentials are required."})
        return attrs
