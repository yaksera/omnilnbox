"""Role-based access control.

             Owner  Admin  Supervisor  Agent
billing        x
channels       x      x
team           x      x*
settings       x      x
saved replies  x      x       x
tags           x      x       x
analytics      x      x       x
see all convs  x      x       x        (x unless "agents see only their own" is on)
assign others  x      x       x
reply/notes    x      x       x         x

* admins can manage supervisors and agents, but not the owner or other admins.
"""
from rest_framework.exceptions import APIException, PermissionDenied

from .models import Membership
from .tenancy import get_membership

O, A, S, G = Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_SUPERVISOR, Membership.ROLE_AGENT

CAPABILITIES = {
    "manage_billing": {O},
    "manage_channels": {O, A},
    "manage_team": {O, A},
    "manage_settings": {O, A},
    "manage_canned": {O, A, S},
    "manage_tags": {O, A, S},
    "view_analytics": {O, A, S},
    "see_all_conversations": {O, A, S},
    "assign_others": {O, A, S},
    "publish_posts": {O, A, S},        # agents can write drafts; supervisors+ publish/schedule
    "manage_social_accounts": {O, A},
    "manage_automations": {O, A},
    "view_audit_log": {O, A},
    "manage_products": {O, A, S},      # catalog; every role can create orders
    "manage_shop": {O, A},
    "send_broadcasts": {O, A, S},
    "manage_developers": {O, A},       # API keys and webhooks             # payment gateway keys, courier accounts, order messages      # AI assistant settings, knowledge base, automation rules
}


class PlanUpgradeRequired(APIException):
    status_code = 402
    default_code = "upgrade_required"
    default_detail = "Your current plan doesn't include this feature. Upgrade to use it."


def capabilities_for(role):
    return sorted(cap for cap, roles in CAPABILITIES.items() if role in roles)


def require(request, capability):
    m = get_membership(request)
    if m.role not in CAPABILITIES[capability]:
        raise PermissionDenied("Your role doesn't allow this action.")
    return m


def require_feature(workspace, feature):
    from billing.plans import FEATURE_LABELS
    if not workspace.has_feature(feature):
        raise PlanUpgradeRequired(f"{FEATURE_LABELS.get(feature, feature)} is not included in your plan. "
                                  "Upgrade on the Billing page to use it.")
