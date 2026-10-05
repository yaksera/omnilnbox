from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from billing.plans import F_AGENT_SCOPE, F_SUPERVISOR

from accounts.audit import audit
from accounts.models import Profile, PushSubscription
from accounts.views import login_ticket, send_verification

from .models import Invitation, Membership
from .permissions import capabilities_for, require, require_feature
from .serializers import MembershipSerializer, RegisterSerializer, UserSerializer, WorkspaceSerializer
from .tenancy import get_membership

User = get_user_model()
_DUMMY_HASH = make_password("timing-equaliser")


def _tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        send_verification(user)
        return Response({"user": UserSerializer(user).data, **_tokens(user)}, status=status.HTTP_201_CREATED)


class EmailTokenSerializer(TokenObtainPairSerializer):
    """Accept {email, password} (email is stored as the username)."""

    username_field = "email"

    def validate(self, attrs):
        email = attrs.get("email", "").lower().strip()
        user = User.objects.filter(username=email).first()
        if user is None:
            # Hash anyway so response time doesn't reveal whether the email exists
            check_password(attrs.get("password", ""), _DUMMY_HASH)
        request = self.context.get("request")
        if not user or not user.check_password(attrs.get("password", "")) or not user.is_active:
            if user is not None:
                m = user.memberships.select_related("workspace").first()
                audit(request, "auth.login_failed", target=user.email, meta={"email": user.email},
                      workspace=m.workspace if m else None, actor=None)
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed("Invalid email or password.")
        if Profile.objects.filter(user=user, two_factor_enabled=True).exists():
            # Password was right; now ask for the authenticator code (POST auth/2fa/login/)
            return {"two_factor_required": True, "ticket": login_ticket(user)}
        m = user.memberships.select_related("workspace").first()
        audit(request, "auth.login", target=user.email, workspace=m.workspace if m else None, actor=user)
        return {"user": UserSerializer(user).data, **_tokens(user)}


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenSerializer
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_scope = "auth"


class LogoutView(APIView):
    """Revoke a refresh token so it can't be used again."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass  # already invalid/expired: nothing to revoke
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    def get(self, request):
        membership = get_membership(request, allow_suspended=True)  # the app shows a "suspended" screen
        memberships = Membership.objects.select_related("workspace").filter(user=request.user)
        profile = Profile.of(request.user)
        return Response({
            "user": {**UserSerializer(request.user).data, "email_verified": profile.email_verified,
                     "two_factor_enabled": profile.two_factor_enabled,
                     "push_devices": PushSubscription.objects.filter(user=request.user).count(),
                     "is_platform_admin": request.user.is_staff, "language": profile.language},
            "workspace": WorkspaceSerializer(membership.workspace).data,
            "role": membership.role,
            "capabilities": capabilities_for(membership.role),
            "memberships": MembershipSerializer(memberships, many=True).data,
        })

    def patch(self, request):
        """Update your own profile (name) or password."""
        user = request.user
        name = request.data.get("name")
        if name is not None:
            first, _, last = str(name).strip()[:150].partition(" ")
            user.first_name, user.last_name = first, last
        if request.data.get("new_password"):
            if not user.check_password(request.data.get("current_password", "")):
                return Response({"current_password": ["Incorrect password."]}, status=400)
            try:
                validate_password(request.data["new_password"], user)
            except DjangoValidationError as exc:
                return Response({"new_password": list(exc.messages)}, status=400)
            user.set_password(request.data["new_password"])
            audit(request, "auth.password_changed", target=user.email)
        if request.data.get("language") in ("en", "ne"):
            Profile.objects.update_or_create(user=user, defaults={"language": request.data["language"]})
        user.save()
        return Response(UserSerializer(user).data)


class WorkspaceView(APIView):
    def patch(self, request):
        membership = require(request, "manage_settings")
        ws = membership.workspace
        if "agents_see_all" in request.data and not request.data.get("agents_see_all"):
            require_feature(ws, F_AGENT_SCOPE)
        if request.data.get("csat_enabled") in (True, "true", 1):
            from billing.plans import F_CSAT
            require_feature(ws, F_CSAT)
        ser = WorkspaceSerializer(ws, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        audit(request, "workspace.updated", target=ws.name, meta={k: str(v)[:80] for k, v in ser.validated_data.items()})
        return Response(ser.data)


def _seats_used(ws):
    pending = Invitation.objects.filter(workspace=ws, accepted_at__isnull=True, expires_at__gt=timezone.now()).count()
    return Membership.objects.filter(workspace=ws).count() + pending


def _can_grant(actor, role, ws):
    """Which roles can this member hand out?"""
    if role not in dict(Membership.ROLE_CHOICES) or role == Membership.ROLE_OWNER:
        return False, "Role must be admin, supervisor or agent."
    if role == Membership.ROLE_ADMIN and actor.role != Membership.ROLE_OWNER:
        return False, "Only the owner can make someone an admin."
    if role == Membership.ROLE_SUPERVISOR and not ws.has_feature(F_SUPERVISOR):
        return False, "The Supervisor role is available on Pro and higher plans."
    return True, ""


def _invite_payload(inv):
    return {"id": str(inv.id), "email": inv.email, "role": inv.role, "expires_at": inv.expires_at,
            "url": inv.url, "invited_by": inv.invited_by.email if inv.invited_by else None}


class TeamView(APIView):
    """GET members + pending invites. POST {email, role} creates an invite link."""

    def get(self, request):
        me = get_membership(request)
        ws = me.workspace
        members = Membership.objects.select_related("user").filter(workspace=ws).order_by("created_at")
        can_manage = me.role in ("owner", "admin")
        invites = Invitation.objects.filter(workspace=ws, accepted_at__isnull=True, expires_at__gt=timezone.now())
        return Response({
            "members": [{"role": m.role, "joined_at": m.created_at, **UserSerializer(m.user).data} for m in members],
            "invites": [_invite_payload(i) for i in invites] if can_manage else [],
            "seats_used": _seats_used(ws),
            "seat_limit": ws.seat_limit,
        })

    def post(self, request):
        me = require(request, "manage_team")
        ws = me.workspace
        email = (request.data.get("email") or "").lower().strip()
        try:
            validate_email(email)
        except DjangoValidationError:
            return Response({"email": ["Enter a valid email address."]}, status=400)
        role = request.data.get("role", Membership.ROLE_AGENT)
        ok, why = _can_grant(me, role, ws)
        if not ok:
            return Response({"role": [why]}, status=400 if "Role must" in why else 403)
        if Membership.objects.filter(workspace=ws, user__username=email).exists():
            return Response({"email": ["This person is already a member."]}, status=400)
        if _seats_used(ws) >= ws.seat_limit:
            return Response({"detail": f"Your plan includes {ws.seat_limit} seat(s) and all are in use. "
                                       "Upgrade or add seats on the Billing page."}, status=402)
        Invitation.objects.filter(workspace=ws, email=email, accepted_at__isnull=True).delete()
        inv = Invitation.objects.create(workspace=ws, email=email, role=role, invited_by=request.user)
        emailed = _send_invite_email(inv, request.user)
        audit(request, "team.invited", target=email, meta={"role": role})
        return Response({**_invite_payload(inv), "emailed": emailed}, status=201)


def _send_invite_email(inv, inviter):
    """Email the invite link when SMTP is configured; otherwise the admin copies the link."""
    if not getattr(settings, "EMAIL_HOST", ""):
        return False
    try:
        send_mail(
            subject=f"{inviter.get_full_name() or inviter.email} invited you to {inv.workspace.name} on OmniInbox",
            message=f"You've been invited to join {inv.workspace.name} as {inv.get_role_display()}.\n\n"
                    f"Accept the invitation: {inv.url}\n\nThis link expires in 7 days.",
            from_email=None, recipient_list=[inv.email], fail_silently=False,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


class InviteRevokeView(APIView):
    def delete(self, request, invite_id):
        me = require(request, "manage_team")
        Invitation.objects.filter(workspace=me.workspace, id=invite_id, accepted_at__isnull=True).delete()
        audit(request, "team.invite_revoked", target=str(invite_id))
        return Response(status=204)


class MemberView(APIView):
    """PATCH {role} changes a member's role; DELETE removes them from the workspace."""

    def _target(self, request, user_id):
        me = require(request, "manage_team")
        target = Membership.objects.select_related("user").filter(workspace=me.workspace, user_id=user_id).first()
        if target is None:
            raise NotFound("Member not found.")
        if target.role == Membership.ROLE_OWNER:
            raise PermissionDenied("The owner can't be changed or removed.")
        if me.role != Membership.ROLE_OWNER and target.rank >= me.rank:
            raise PermissionDenied("You can only manage members below your role.")
        return me, target

    def patch(self, request, user_id):
        me, target = self._target(request, user_id)
        role = request.data.get("role")
        ok, why = _can_grant(me, role, me.workspace)
        if not ok:
            return Response({"role": [why]}, status=400 if "Role must" in why else 403)
        old = target.role
        target.role = role
        target.save(update_fields=["role"])
        audit(request, "team.role_changed", target=target.user.email, meta={"from": old, "to": role})
        return Response({"role": target.role, **UserSerializer(target.user).data})

    def delete(self, request, user_id):
        me, target = self._target(request, user_id)
        from inbox.models import Conversation
        Conversation.objects.filter(workspace=me.workspace, assigned_to=target.user).update(assigned_to=None)
        target.delete()
        audit(request, "team.removed", target=target.user.email)
        return Response(status=204)


class InviteAcceptView(APIView):
    """Public: GET shows the invite; POST accepts it.

    New users send {name, password}. Existing users must be logged in as the invited email.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def get_throttles(self):
        # Viewing an invite is harmless; only rate-limit accepting (password attempts)
        return super().get_throttles() if self.request.method == "POST" else []

    def _invite(self, token):
        inv = Invitation.objects.select_related("workspace").filter(token=token).first()
        if inv is None or not inv.is_valid:
            raise NotFound("This invitation is invalid or has expired.")
        return inv

    def get(self, request, token):
        inv = self._invite(token)
        return Response({"workspace": inv.workspace.name, "email": inv.email, "role": inv.role,
                         "user_exists": User.objects.filter(username=inv.email).exists()})

    @transaction.atomic
    def post(self, request, token):
        inv = self._invite(token)
        user = User.objects.filter(username=inv.email).first()
        if user is None:
            ser = RegisterSerializer(data={"name": request.data.get("name", ""), "email": inv.email,
                                           "password": request.data.get("password", "")})
            ser.is_valid(raise_exception=True)
            first, _, last = ser.validated_data["name"].strip().partition(" ")
            user = User.objects.create_user(username=inv.email, email=inv.email,
                                            password=ser.validated_data["password"], first_name=first, last_name=last)
        elif not (request.user.is_authenticated and request.user.pk == user.pk):
            if not user.check_password(request.data.get("password", "")):
                return Response({"password": ["Log in with the password for this email to accept."]}, status=400)
        Membership.objects.get_or_create(user=user, workspace=inv.workspace, defaults={"role": inv.role})
        inv.accepted_at = timezone.now()
        inv.save(update_fields=["accepted_at"])
        audit(request, "team.joined", target=user.email, meta={"role": inv.role}, workspace=inv.workspace, actor=user)
        return Response({"workspace_id": str(inv.workspace_id), "user": UserSerializer(user).data, **_tokens(user)})
