"""Web Push (RFC 8030) with message encryption (RFC 8291, aes128gcm) and VAPID (RFC 8292).

Implemented with `cryptography` only (pywebpush's http-ece dependency often fails to build on Windows).
"""
import base64
import json
import logging
import os
import struct
import time
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _raw_public(key) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def _hkdf(salt, ikm, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


# ------------------------------------------------------------------ VAPID keys
def vapid_keys():
    """(private_key, public_key_b64url). Generated once and stored encrypted in the database."""
    from .models import ServerKey
    row = ServerKey.objects.filter(name="vapid").first()
    if row is None:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
        row, _ = ServerKey.objects.get_or_create(name="vapid", defaults={"value": {"pem": pem}})
    key = serialization.load_pem_private_key(row.value["pem"].encode(), password=None)
    return key, b64u(_raw_public(key))


def vapid_header(endpoint, key, public_b64, subject):
    aud = "{0.scheme}://{0.netloc}".format(urlparse(endpoint))
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": aud, "exp": int(time.time()) + 12 * 3600, "sub": subject},
                             separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    jwt = f"{header}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={public_b64}"


# ------------------------------------------------------------------ encryption
def encrypt(payload: bytes, p256dh_b64: str, auth_b64: str, salt=None, server_key=None) -> bytes:
    ua_public = unb64u(p256dh_b64)
    auth_secret = unb64u(auth_b64)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _raw_public(server_key)
    shared = server_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public))
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # single record, delimiter 0x02
    return salt + struct.pack(">I", 4096) + bytes([len(as_public)]) + as_public + ciphertext


def decrypt(body: bytes, ua_private, auth_b64: str) -> bytes:
    """Receiver side (used by tests to prove the encryption is correct)."""
    salt, idlen = body[:16], body[20]
    as_public = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    ua_public = _raw_public(ua_private)
    shared = ua_private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = _hkdf(unb64u(auth_b64), shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, ciphertext, None)
    return plain.rstrip(b"\x00")[:-1]


def send(subscription, data: dict, ttl=86400):
    """Send one notification. Returns False if the subscription is gone (and deletes it)."""
    from django.conf import settings
    key, public = vapid_keys()
    body = encrypt(json.dumps(data).encode(), subscription.p256dh, subscription.auth)
    subject = f"mailto:{getattr(settings, 'PUSH_CONTACT_EMAIL', '') or 'admin@example.com'}"
    try:
        resp = requests.post(subscription.endpoint, data=body, timeout=15, headers={
            "Authorization": vapid_header(subscription.endpoint, key, public, subject),
            "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
            "TTL": str(ttl), "Urgency": "high",
        })
    except requests.RequestException as exc:
        logger.warning("Push to %s failed: %s", urlparse(subscription.endpoint).netloc, exc)
        return True
    if resp.status_code in (404, 410):  # unsubscribed / expired
        subscription.delete()
        return False
    if resp.status_code >= 400:
        logger.warning("Push service answered %s: %s", resp.status_code, resp.text[:200])
    return True
