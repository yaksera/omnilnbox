"""Helpers to resolve the active workspace for a request."""
import uuid

from rest_framework.exceptions import PermissionDenied

from .models import Membership


class WorkspaceSuspended(PermissionDenied):
    default_code = "workspace_suspended"
    default_detail = "This workspace has been suspended. Please contact OmniInbox support."


def get_membership(request, allow_suspended=False) -> Membership:
    """Return the caller's membership for the active workspace.

    The client may pick a workspace with the `X-Workspace-Id` header; otherwise the
    user's first (oldest) workspace is used.
    """
    cached = getattr(request, "_membership", None)
    if cached is not None:
        if cached.workspace.suspended_at and not allow_suspended:
            raise WorkspaceSuspended(_suspended_detail(cached.workspace))
        return cached
    qs = Membership.objects.select_related("workspace").filter(user=request.user)
    ws_id = request.headers.get("X-Workspace-Id")
    if ws_id:
        try:
            uuid.UUID(ws_id)
        except ValueError:
            raise PermissionDenied("Invalid workspace id.")
        qs = qs.filter(workspace_id=ws_id)
    membership = qs.order_by("created_at").first()
    if membership is None:
        raise PermissionDenied("You are not a member of this workspace.")
    request._membership = membership
    if membership.workspace.suspended_at and not allow_suspended:
        raise WorkspaceSuspended(_suspended_detail(membership.workspace))
    return membership


def _suspended_detail(ws):
    reason = f" Reason: {ws.suspended_reason}" if ws.suspended_reason else ""
    return f"This workspace has been suspended.{reason} Please contact OmniInbox support."


def get_workspace(request):
    return get_membership(request).workspace


class WorkspaceScopedMixin:
    """Mixin for viewsets whose queryset has a `workspace` FK."""

    def get_workspace(self):
        return get_workspace(self.request)

    def get_queryset(self):
        return super().get_queryset().filter(workspace=self.get_workspace())
