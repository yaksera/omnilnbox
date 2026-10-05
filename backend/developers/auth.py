"""API-key authentication: `Authorization: Bearer omni_…` or `X-Api-Key: omni_…`.

A key acts as the teammate who created it (same role and permissions) inside the key's workspace.
"""
from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import ApiKey, hash_key


class ApiKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        raw = request.headers.get("X-Api-Key", "")
        header = request.headers.get("Authorization", "")
        if not raw and header.lower().startswith("bearer omni_"):
            raw = header.split(" ", 1)[1].strip()
        if not raw.startswith("omni_"):
            return None  # not an API key: let JWT handle it
        key = ApiKey.objects.select_related("workspace", "created_by").filter(key_hash=hash_key(raw), revoked_at__isnull=True).first()
        if key is None or not key.created_by.is_active:
            raise exceptions.AuthenticationFailed("Invalid or revoked API key.")
        from billing.plans import F_API
        if not key.workspace.has_feature(F_API):
            raise exceptions.AuthenticationFailed("API access is not included in this workspace's plan.")
        from core.models import Membership
        membership = Membership.objects.select_related("workspace").filter(user=key.created_by, workspace=key.workspace).first()
        if membership is None:
            raise exceptions.AuthenticationFailed("The key's owner is no longer a member of this workspace.")
        request._membership = membership  # pin the key's workspace (X-Workspace-Id is ignored)
        if not key.last_used_at or (timezone.now() - key.last_used_at).total_seconds() > 60:
            ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return key.created_by, key

    def authenticate_header(self, request):
        return "Bearer"
