"""audit(request, "channel.connected", target="WhatsApp: Shop") records who did what, from where."""
import logging

logger = logging.getLogger(__name__)

LABELS = {
    "auth.login": "Logged in",
    "auth.login_failed": "Failed login",
    "auth.logout_all": "Logged out of all devices",
    "platform.suspend": "Workspace suspended by OmniInbox",
    "platform.unsuspend": "Workspace reactivated by OmniInbox",
    "platform.extend": "Plan extended by OmniInbox",
    "auth.password_changed": "Changed password",
    "auth.password_reset": "Reset password by email",
    "auth.2fa_enabled": "Turned on two-factor login",
    "auth.2fa_disabled": "Turned off two-factor login",
    "team.invited": "Invited a teammate",
    "team.invite_revoked": "Revoked an invite",
    "team.joined": "Joined the workspace",
    "team.role_changed": "Changed a role",
    "team.removed": "Removed a teammate",
    "workspace.updated": "Changed workspace settings",
    "channel.connected": "Connected a channel",
    "channel.updated": "Updated a channel",
    "channel.removed": "Removed a channel",
    "billing.plan_changed": "Changed plan",
    "billing.paid": "Paid",
    "ai.settings_changed": "Changed AI settings",
    "automation.created": "Created an automation",
    "automation.updated": "Updated an automation",
    "automation.deleted": "Deleted an automation",
    "social.connected": "Connected a publishing account",
    "social.removed": "Removed a publishing account",
    "api_key.created": "Created an API key",
    "api_key.revoked": "Revoked an API key",
    "webhook.created": "Added a webhook",
    "webhook.deleted": "Deleted a webhook",
    "export.csv": "Exported conversations",
    "order.status": "Changed an order status",
    "payments.settings_changed": "Changed payment settings",
    "delivery.settings_changed": "Changed delivery settings",
    "broadcast.sent": "Sent a broadcast",
}


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")
    return ip or None


def audit(request, action, target="", meta=None, workspace=None, actor=None):
    """Never raises: logging must not break the action it records."""
    from .models import AuditLog
    try:
        user = actor or (getattr(request, "user", None) if request is not None else None)
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        if workspace is None and request is not None and user is not None:
            try:
                from core.tenancy import get_membership
                workspace = get_membership(request).workspace
            except Exception:  # noqa: BLE001
                workspace = None
        label = (user.get_full_name() or user.email) if user else (meta or {}).get("email", "")
        AuditLog.objects.create(workspace=workspace, actor=user, actor_label=label[:200], action=action,
                                target=str(target)[:300], meta=meta or {}, ip=client_ip(request))
    except Exception:  # noqa: BLE001
        logger.exception("Could not write audit log entry %s", action)
