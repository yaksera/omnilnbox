"""JWT authentication that also honours "log out of all devices".

SimpleJWT access tokens are stateless, so revoking refresh tokens alone would leave other devices signed in until
their access token expires. Here an access token issued before Profile.sessions_revoked_at is rejected.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import Profile


class RevocableJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        revoked = Profile.objects.filter(user_id=user.pk).values_list("sessions_revoked_at", flat=True).first()
        if revoked and int(validated_token.get("iat", 0)) <= int(revoked.timestamp()):
            raise InvalidToken("This session was signed out. Please log in again.")
        return user
