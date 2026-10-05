"""Encryption helpers for storing channel credentials (tokens, passwords) at rest."""
import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        # Derive a stable key from SECRET_KEY for development. Set FIELD_ENCRYPTION_KEY in production!
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


class EncryptedJSONField(models.TextField):
    """Stores a dict as Fernet-encrypted JSON text."""

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return {}
        try:
            return json.loads(decrypt(value))
        except (InvalidToken, ValueError):
            return {}

    def to_python(self, value):
        if isinstance(value, dict):
            return value
        if value in (None, ""):
            return {}
        try:
            return json.loads(decrypt(value))
        except (InvalidToken, ValueError):
            return {}

    def get_prep_value(self, value):
        if value is None:
            value = {}
        return encrypt(json.dumps(value))
