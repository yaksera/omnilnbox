from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.plans import F_AUDIT
from core.permissions import require, require_feature
from core.tenancy import get_membership

from . import mail, totp, webpush
from .audit import LABELS, audit
from .models import AuditLog, Profile, PushSubscription

User = get_user_model()
VERIFY_SALT, TWOFA_SALT = "omni.verify-email", "omni.2fa-login"


def _dev_link(link):
    """In local development without SMTP, hand the link back so the UI can show it."""
    return {"dev_link": link} if settings.DEBUG and not settings.EMAIL_HOST else {}


def _revoke_sessions(user):
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    for tok in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=tok)
    # Also invalidate access tokens that are still within their lifetime (see accounts.auth).
    Profile.objects.update_or_create(user=user, defaults={"sessions_revoked_at": timezone.now().replace(microsecond=0)})


# ------------------------------------------------------------------ password reset
class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        email = str(request.data.get("email") or "").lower().strip()
        user = User.objects.filter(username=email, is_active=True).first()
        extra = {}
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={default_token_generator.make_token(user)}"
            mail.send(user.email, "Reset your OmniInbox password", [
                f"Hi {user.first_name or 'there'},",
                "Someone (hopefully you) asked to reset the password for your OmniInbox account. "
                "The link below works once and expires in 3 days.",
                "If you didn't ask for this, you can ignore this email: your password stays the same.",
            ], ("Choose a new password", link))
            extra = _dev_link(link)
        # Same answer whether or not the email exists (no account enumeration)
        return Response({"ok": True, "detail": "If an account exists for that email, we've sent a reset link.", **extra})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(str(request.data.get("uid", "")))))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError, DjangoValidationError):
            user = None
        if user is None or not default_token_generator.check_token(user, str(request.data.get("token", ""))):
            return Response({"detail": "This reset link is invalid or has expired. Ask for a new one."}, status=400)
        password = str(request.data.get("password") or "")
        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=400)
        user.set_password(password)
        user.save()
        _revoke_sessions(user)  # log out everywhere
        Profile.objects.filter(user=user).update(email_verified=True)  # they proved they own the inbox
        m = user.memberships.select_related("workspace").first()
        audit(request, "auth.password_reset", target=user.email, workspace=m.workspace if m else None, actor=user)
        return Response({"ok": True})


# ------------------------------------------------------------------ email verification
def send_verification(user):
    token = signing.dumps({"u": user.pk, "e": user.email}, salt=VERIFY_SALT)
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    mail.send(user.email, "Confirm your email for OmniInbox", [
        f"Hi {user.first_name or 'there'}, welcome to OmniInbox!",
        "Please confirm your email address so we can send you password resets and alerts about waiting customers.",
    ], ("Confirm my email", link))
    return link


class SendVerificationView(APIView):
    throttle_scope = "auth"

    def post(self, request):
        if Profile.of(request.user).email_verified:
            return Response({"ok": True, "already": True})
        return Response({"ok": True, **_dev_link(send_verification(request.user))})


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        try:
            data = signing.loads(str(request.data.get("token", "")), salt=VERIFY_SALT, max_age=7 * 24 * 3600)
        except signing.BadSignature:
            return Response({"detail": "This confirmation link is invalid or has expired."}, status=400)
        user = User.objects.filter(pk=data.get("u"), email=data.get("e")).first()
        if not user:
            return Response({"detail": "This confirmation link is no longer valid."}, status=400)
        Profile.objects.update_or_create(user=user, defaults={"email_verified": True})
        return Response({"ok": True, "email": user.email})


# ------------------------------------------------------------------ two-factor login
class TwoFactorSetupView(APIView):
    """POST: start setup (new secret + QR). The secret is only active after /enable/ confirms a code."""

    def post(self, request):
        profile = Profile.of(request.user)
        if profile.two_factor_enabled:
            return Response({"detail": "Two-factor login is already on."}, status=400)
        secret = totp.new_secret()
        profile.two_factor = {**profile.two_factor, "pending": secret}
        profile.save(update_fields=["two_factor"])
        uri = totp.provisioning_uri(secret, request.user.email)
        return Response({"secret": secret, "uri": uri, "qr_svg": totp.qr_svg(uri)})


class TwoFactorEnableView(APIView):
    throttle_scope = "auth"

    def post(self, request):
        profile = Profile.of(request.user)
        secret = profile.two_factor.get("pending")
        if not secret or not totp.verify(secret, request.data.get("code", "")):
            return Response({"code": ["That code isn't right. Check the time on your phone and try the newest code."]},
                            status=400)
        codes = totp.new_recovery_codes()
        profile.two_factor = {"secret": secret, "recovery": [totp.hash_code(c) for c in codes]}
        profile.two_factor_enabled = True
        profile.save(update_fields=["two_factor", "two_factor_enabled"])
        audit(request, "auth.2fa_enabled", target=request.user.email)
        return Response({"ok": True, "recovery_codes": codes})


class TwoFactorDisableView(APIView):
    throttle_scope = "auth"

    def post(self, request):
        if not request.user.check_password(str(request.data.get("password", ""))):
            return Response({"password": ["Incorrect password."]}, status=400)
        profile = Profile.of(request.user)
        profile.two_factor, profile.two_factor_enabled = {}, False
        profile.save(update_fields=["two_factor", "two_factor_enabled"])
        audit(request, "auth.2fa_disabled", target=request.user.email)
        return Response({"ok": True})


class LogoutAllView(APIView):
    """Sign this user out everywhere: every refresh token (all browsers, phones, API sessions) is revoked."""

    throttle_scope = "auth"

    def post(self, request):
        _revoke_sessions(request.user)
        audit(request, "auth.logout_all", target=request.user.email)
        return Response({"ok": True})


def check_second_factor(profile, code):
    """True for a valid authenticator code or an unused recovery code (which is then used up)."""
    tf = profile.two_factor or {}
    if totp.verify(tf.get("secret", ""), code):
        return True
    hashed = totp.hash_code(str(code))
    if hashed in tf.get("recovery", []):
        tf["recovery"] = [h for h in tf["recovery"] if h != hashed]
        profile.two_factor = tf
        profile.save(update_fields=["two_factor"])
        return True
    return False


def login_ticket(user):
    return signing.dumps({"u": user.pk}, salt=TWOFA_SALT)


class TwoFactorLoginView(APIView):
    """Second step of login: {ticket, code} -> tokens."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        from core.views import _tokens
        from core.serializers import UserSerializer
        try:
            data = signing.loads(str(request.data.get("ticket", "")), salt=TWOFA_SALT, max_age=300)
        except signing.BadSignature:
            return Response({"detail": "Your login took too long. Enter your password again."}, status=400)
        user = User.objects.filter(pk=data.get("u"), is_active=True).first()
        profile = Profile.objects.filter(user=user).first() if user else None
        if not profile or not profile.two_factor_enabled or not check_second_factor(profile, request.data.get("code", "")):
            return Response({"code": ["That code isn't right."]}, status=400)
        m = user.memberships.select_related("workspace").first()
        audit(request, "auth.login", target=user.email, meta={"two_factor": True}, workspace=m.workspace if m else None,
              actor=user)
        return Response({"user": UserSerializer(user).data, **_tokens(user)})


# ------------------------------------------------------------------ notifications
class PushKeyView(APIView):
    def get(self, request):
        return Response({"public_key": webpush.vapid_keys()[1]})


class PushSubscribeView(APIView):
    def post(self, request):
        endpoint = str(request.data.get("endpoint") or "")
        keys = request.data.get("keys") or {}
        if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
            return Response({"detail": "Invalid push subscription."}, status=400)
        PushSubscription.objects.update_or_create(endpoint=endpoint[:1000], defaults={
            "user": request.user, "p256dh": str(keys["p256dh"])[:200], "auth": str(keys["auth"])[:100],
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300]})
        return Response({"ok": True}, status=201)

    def delete(self, request):
        PushSubscription.objects.filter(user=request.user, endpoint=str(request.data.get("endpoint") or "")).delete()
        return Response(status=204)


class PushTestView(APIView):
    throttle_scope = "auth"

    def post(self, request):
        subs = list(PushSubscription.objects.filter(user=request.user))
        if not subs:
            return Response({"detail": "Turn on notifications on this device first."}, status=400)
        for sub in subs:
            webpush.send(sub, {"title": "OmniInbox notifications work 🎉", "body": "You'll get new customer messages here.",
                               "url": "/inbox", "tag": "test"})
        return Response({"ok": True, "devices": len(subs)})


class NotificationPrefsView(APIView):
    def get(self, request):
        profile = Profile.of(request.user)
        ws = get_membership(request).workspace
        return Response({"email_unanswered": profile.notify_email_unanswered,
                         "push_devices": PushSubscription.objects.filter(user=request.user).count(),
                         "unanswered_alert_minutes": ws.unanswered_alert_minutes})

    def put(self, request):
        profile = Profile.of(request.user)
        if "email_unanswered" in request.data:
            profile.notify_email_unanswered = bool(request.data["email_unanswered"])
            profile.save(update_fields=["notify_email_unanswered"])
        return self.get(request)


# ------------------------------------------------------------------ activity log
class AuditLogView(APIView):
    def get(self, request):
        m = require(request, "view_audit_log")
        require_feature(m.workspace, F_AUDIT)
        qs = AuditLog.objects.filter(workspace=m.workspace)
        if request.query_params.get("action"):
            qs = qs.filter(action__startswith=request.query_params["action"][:40])
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1
        rows = qs[(page - 1) * 50: page * 50 + 1]
        return Response({
            "results": [{"id": r.id, "action": r.action, "label": LABELS.get(r.action, r.action), "actor": r.actor_label,
                         "target": r.target, "meta": r.meta, "ip": r.ip, "created_at": r.created_at} for r in rows[:50]],
            "has_more": len(rows) > 50, "page": page,
        })


# ------------------------------------------------------------------ setup checklist
class OnboardingView(APIView):
    def get(self, request):
        from automations.models import AssistantSettings, KnowledgeItem, Rule
        from core.models import Invitation
        from inbox.models import Message
        m = get_membership(request)
        ws, profile = m.workspace, Profile.of(request.user)
        admin = m.role in ("owner", "admin")
        ai = AssistantSettings.objects.filter(workspace=ws).first()
        steps = [
            {"key": "verify_email", "title": "Confirm your email", "done": profile.email_verified, "href": None,
             "help": "So you can reset your password and get alerts."},
        ]
        if admin:
            steps += [
                {"key": "connect_channel", "title": "Connect your first channel", "href": "/channels",
                 "done": ws.channels.filter(is_demo=False).exists(),
                 "help": "WhatsApp, Messenger, Instagram, TikTok, Telegram, Viber, email or your website."},
                {"key": "business_info", "title": "Tell the AI about your business", "href": "/automations",
                 "done": bool(ai and ai.about.strip()), "help": "What you sell, delivery and payment options."},
                {"key": "knowledge", "title": "Add 3 knowledge base entries", "href": "/automations#knowledge",
                 "done": KnowledgeItem.objects.filter(workspace=ws).count() >= 3,
                 "help": "Prices, delivery charges, return policy: the questions customers ask most."},
                {"key": "automation", "title": "Turn on the AI chatbot or an automation", "href": "/automations#rules",
                 "done": bool(ai and ai.bot_mode != "off") or Rule.objects.filter(workspace=ws, enabled=True).exists(),
                 "help": "Answer 24/7, or send an instant reply to comments and keywords."},
                {"key": "invite_team", "title": "Invite your team", "href": "/team",
                 "done": ws.memberships.count() > 1 or Invitation.objects.filter(workspace=ws).exists(),
                 "help": "Give each person their own login and role."},
            ]
        steps += [
            {"key": "notifications", "title": "Get notified of new messages", "href": "/settings#notifications",
             "done": PushSubscription.objects.filter(user=request.user).exists(),
             "help": "Phone and desktop notifications, even when OmniInbox is closed."},
            {"key": "first_reply", "title": "Reply to a customer", "href": "/inbox",
             "done": Message.objects.filter(conversation__workspace=ws, sent_by=request.user, is_note=False).exists(),
             "help": "Replies go back on the customer's own app."},
        ]
        return Response({"steps": steps, "done": sum(s["done"] for s in steps), "total": len(steps),
                         "dismissed": profile.onboarding_dismissed})

    def post(self, request):
        Profile.objects.update_or_create(user=request.user,
                                         defaults={"onboarding_dismissed": bool(request.data.get("dismissed", True))})
        return self.get(request)


__all__ = ["status"]
