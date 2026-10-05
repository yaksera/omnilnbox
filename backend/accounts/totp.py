"""RFC 6238 TOTP (Google Authenticator, Authy, Microsoft Authenticator...). No extra dependency."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP, DIGITS = 30, 6


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def now_code(secret, at=None):
    return _code(secret, int((at or time.time()) // STEP))


def verify(secret, code, window=1, at=None):
    """Accept the current code and one step either side (clock drift)."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS or not secret:
        return False
    counter = int((at or time.time()) // STEP)
    return any(hmac.compare_digest(_code(secret, counter + d), code) for d in range(-window, window + 1))


def provisioning_uri(secret, email, issuer="OmniInbox"):
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"


def qr_svg(text):
    import io
    import qrcode
    import qrcode.image.svg
    buf = io.BytesIO()
    qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2).save(buf)
    return buf.getvalue().decode()


def new_recovery_codes(n=10):
    return [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(n)]


def hash_code(code):
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
