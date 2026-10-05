from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import Membership, Workspace

User = get_user_model()


class WorkspaceSerializer(serializers.ModelSerializer):
    effective_plan = serializers.CharField(read_only=True)
    plan_name = serializers.SerializerMethodField()
    channel_limit = serializers.IntegerField(read_only=True)
    seat_limit = serializers.IntegerField(read_only=True)
    is_trialing = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    features = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            "id", "name", "slug", "plan", "effective_plan", "plan_name", "billing_cycle", "plan_expires_at",
            "trial_ends_at", "is_trialing", "is_expired", "extra_seats", "currency", "channel_limit", "seat_limit",
            "features", "agents_see_all", "unanswered_alert_minutes", "sla_minutes", "csat_enabled", "csat_question",
            "brand", "suspended", "created_at",
        ]
        read_only_fields = [f for f in fields if f not in (
            "name", "agents_see_all", "currency", "unanswered_alert_minutes", "sla_minutes", "csat_enabled", "csat_question")]

    brand = serializers.SerializerMethodField()
    suspended = serializers.SerializerMethodField()

    def get_suspended(self, obj):
        return {"at": obj.suspended_at, "reason": obj.suspended_reason} if obj.suspended_at else None

    def get_brand(self, obj):
        """White-label settings (empty when the plan doesn't include it)."""
        from billing.plans import F_WHITE_LABEL
        if not obj.has_feature(F_WHITE_LABEL):
            return {"name": "", "color": "", "logo_url": "", "hide_powered_by": False}
        from publishing.media import preview_path
        return {"name": obj.brand_name, "color": obj.brand_color,
                "logo_url": preview_path(obj.brand_logo) if obj.brand_logo_id else "", "hide_powered_by": obj.hide_powered_by}

    def validate_sla_minutes(self, value):
        if value and not 5 <= value <= 10080:
            raise serializers.ValidationError("Use 5 to 10080 minutes, or 0 to turn it off.")
        return value

    def validate_unanswered_alert_minutes(self, value):
        if value and not 5 <= value <= 1440:
            raise serializers.ValidationError("Use 5 to 1440 minutes, or 0 to turn alerts off.")
        return value

    def get_plan_name(self, obj):
        return obj.plan_info["name"]

    def get_features(self, obj):
        return obj.plan_info["features"]

    def validate_currency(self, value):
        if value not in ("NPR", "USD"):
            raise serializers.ValidationError("Currency must be NPR or USD.")
        return value


class MembershipSerializer(serializers.ModelSerializer):
    workspace = WorkspaceSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["role", "workspace"]


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "name", "first_name", "last_name"]

    def get_name(self, obj):
        return obj.get_full_name() or obj.email


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    workspace_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    # Affiliate attribution: a promo code typed in, or the code remembered from a tracking link (/r/CODE)
    referral_code = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    referral_source = serializers.ChoiceField(choices=["link", "code"], required=False, default="code")

    def validate(self, data):
        from affiliates.services import find_active
        code = data.get("referral_code", "")
        data["_affiliate"] = find_active(code) if code else None
        # A typed code must be valid; a stale link code (affiliate since removed) is silently ignored.
        if code and data["_affiliate"] is None and data.get("referral_source") == "code":
            raise serializers.ValidationError({"referral_code": ["This promo code isn't valid."]})
        return data

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, data):
        first, _, last = data["name"].strip().partition(" ")
        user = User.objects.create_user(
            username=data["email"], email=data["email"], password=data["password"],
            first_name=first, last_name=last,
        )
        ws = Workspace(name=data.get("workspace_name") or f"{first}'s workspace")
        ws.start_trial()  # every new workspace gets a free trial of the Pro plan
        ws.save()
        Membership.objects.create(user=user, workspace=ws, role=Membership.ROLE_OWNER)
        if data.get("_affiliate"):
            from affiliates.models import Referral
            Referral.objects.create(workspace=ws, affiliate=data["_affiliate"], source=data.get("referral_source", "code"))
        return user
