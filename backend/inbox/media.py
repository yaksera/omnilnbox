"""Photos, videos, voice notes and files in conversations.

Incoming: providers describe each attachment with a `source` (a platform media id or URL). We store an
Attachment row straight away (status "pending") and download the file in the background, so webhooks stay fast.
Outgoing: agents upload files first (POST /api/attachments/), then send a message that references them.

Files are private. The web app and the platforms (which must fetch media from a URL, e.g. Instagram, Viber)
get signed links that expire.
"""
import logging
import mimetypes
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import Attachment

logger = logging.getLogger(__name__)

SALT = "omni.attachment"
MAX_BYTES = int(getattr(settings, "ATTACHMENT_MAX_MB", 25)) * 1024 * 1024
# Types a browser may show inline. Everything else (html, svg, js, exe...) is always downloaded, never rendered.
INLINE = {"image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "video/webm", "video/quicktime",
          "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "audio/webm", "audio/wav", "audio/x-wav",
          "audio/amr", "application/pdf"}
KIND_ALIASES = {"photo": "image", "picture": "image", "image": "image", "sticker": "sticker", "video": "video",
                "animation": "video", "video_note": "video", "audio": "audio", "voice": "voice", "ptt": "voice",
                "document": "file", "file": "file", "fallback": "file", "share": "file"}


def _workers():
    return 1 if settings.DATABASES["default"]["ENGINE"].endswith("sqlite3") else 3


_pool = ThreadPoolExecutor(max_workers=_workers(), thread_name_prefix="media")


# ------------------------------------------------------------------ helpers
def kind_for(mime="", hint=""):
    hint = KIND_ALIASES.get((hint or "").lower().split("/")[0] if "/" in (hint or "") else (hint or "").lower(), "")
    if hint in ("voice", "sticker"):
        return hint
    mime = (mime or "").lower()
    if mime.startswith("image/"):
        return "sticker" if hint == "sticker" else "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "voice" if hint == "voice" else "audio"
    if hint:
        return hint
    return "file"


def extension_for(mime, name=""):
    ext = os.path.splitext(name or "")[1].lower()
    if ext and len(ext) <= 10 and ext[1:].isalnum():
        return ext
    guessed = mimetypes.guess_extension((mime or "").split(";")[0].strip()) or ""
    return {".jpe": ".jpg", ".oga": ".ogg"}.get(guessed, guessed)[:10]


def sniff(head: bytes, fallback=""):
    """Real type from the first bytes (don't trust names or headers for what we render inline)."""
    sigs = [(b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"), (b"GIF8", "image/gif"),
            (b"%PDF", "application/pdf"), (b"OggS", "audio/ogg"), (b"\x1aE\xdf\xa3", "video/webm"),
            (b"ID3", "audio/mpeg"), (b"#!AMR", "audio/amr")]
    for sig, mime in sigs:
        if head.startswith(sig):
            if mime == "video/webm" and fallback.startswith("audio/"):
                return "audio/webm"
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio/mp4"
        return "video/quicktime" if brand == b"qt  " else (fallback if fallback.startswith(("audio/", "video/")) else "video/mp4")
    return (fallback or "application/octet-stream").split(";")[0].strip().lower()


def token(att_id, purpose="view"):
    return signing.TimestampSigner(salt=f"{SALT}.{purpose}").sign(str(att_id)).split(":", 1)[1] + f"-{purpose[0]}"


def read_token(att_id, tok):
    """Valid link for this attachment? Web-app links last 12 h, platform links 3 days."""
    try:
        value, kind = tok.rsplit("-", 1)
    except ValueError:
        return False
    purpose = {"v": "view", "p": "public"}.get(kind)
    if not purpose:
        return False
    try:
        signing.TimestampSigner(salt=f"{SALT}.{purpose}").unsign(f"{att_id}:{value}",
                                                                 max_age=12 * 3600 if purpose == "view" else 3 * 86400)
        return True
    except signing.BadSignature:
        return False


def view_url(att):
    """Link for the web app (through the /backend proxy)."""
    return f"/backend/attachments/{att.id}/{token(att.id, 'view')}/"


def public_url(att):
    """Link a platform (Instagram, Viber...) can fetch; needs PUBLIC_BASE_URL to be reachable from the internet."""
    return f"{settings.PUBLIC_BASE_URL}/api/attachments/{att.id}/{token(att.id, 'public')}/"


def as_json(att):
    return {"id": str(att.id), "kind": att.kind, "name": att.name, "mime": att.mime, "size": att.size,
            "status": att.status, "error": att.error if att.status == Attachment.FAILED else "",
            "url": view_url(att) if att.status == Attachment.READY else "",
            "transcript": att.transcript,
            "ai": {"is_payment": bool(att.ai_note.get("is_payment")), "description": att.ai_note.get("description", "")}
            if att.ai_note else None}


def message_files(msg):
    """Attachments for the API; falls back to the old summary JSON for messages stored before files existed."""
    files = list(msg.files.all())
    if files:
        return [as_json(a) for a in files]
    return [{"id": "", "kind": kind_for("", a.get("type", "")), "name": a.get("name") or "", "mime": "", "size": 0,
             "status": "unavailable", "error": "", "url": ""} for a in (msg.attachments or []) if isinstance(a, dict)]


def store_bytes(att, data, mime="", name=""):
    if len(data) > MAX_BYTES:
        raise ValueError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    att.mime = sniff(data[:64], mime or att.mime)
    att.name = (name or att.name or f"{att.kind}{extension_for(att.mime)}")[:255]
    att.kind = kind_for(att.mime, att.kind)
    att.extension = extension_for(att.mime, att.name)
    att.size = len(data)
    att.file.save(f"x{att.extension}", ContentFile(data), save=False)
    att.status, att.error = Attachment.READY, ""
    att.save()
    return att


def download_url(url, headers=None):
    """Stream a file with a hard size limit."""
    with requests.get(url, headers=headers or {}, stream=True, timeout=30, allow_redirects=True) as resp:
        if resp.status_code >= 400:
            raise ValueError(f"Download failed ({resp.status_code}).")
        chunks, total = [], 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
            chunks.append(chunk)
        name = ""
        disp = resp.headers.get("Content-Disposition", "")
        if "filename=" in disp:
            name = disp.split("filename=", 1)[1].strip('"; ')
        return b"".join(chunks), resp.headers.get("Content-Type", ""), name


# ------------------------------------------------------------------ incoming
def create_incoming(msg, items):
    """Create Attachment rows for an incoming message; download in the background after commit."""
    created = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        att = Attachment(workspace_id=msg.conversation.workspace_id, message=msg,
                         kind=kind_for(item.get("mime", ""), item.get("type", "")),
                         name=str(item.get("name") or "")[:255], mime=str(item.get("mime") or "")[:120],
                         source={k: v for k, v in item.items() if k in ("id", "url", "file_id", "graph_message_id",
                                                                         "attachment_id")})
        data = item.get("data")
        if isinstance(data, (bytes, bytearray)):  # email: the bytes are already here
            att.save()
            try:
                store_bytes(att, bytes(data), item.get("mime", ""), item.get("name", ""))
            except ValueError as exc:
                att.status, att.error = Attachment.FAILED, str(exc)[:500]
                att.save(update_fields=["status", "error"])
        elif not att.source:
            att.status, att.error = Attachment.FAILED, "The platform didn't share this file."
            att.save()
        else:
            att.save()
            transaction.on_commit(lambda att_id=att.id: _pool.submit(_download_job, att_id))
        created.append(att)
    return created


def _download_job(att_id):
    close_old_connections()
    try:
        download(att_id)
    finally:
        close_old_connections()


def download(att_id):
    from integrations.providers import get_provider
    att = Attachment.objects.select_related("message__conversation__channel").filter(id=att_id).first()
    if not att or att.status != Attachment.PENDING or not att.message:
        return att
    try:
        provider = get_provider(att.message.conversation.channel)
        data, mime, name = provider.fetch_attachment(att.source)
        store_bytes(att, data, mime, name)
    except Exception as exc:  # noqa: BLE001 - keep the message, show "couldn't download"
        logger.warning("Attachment %s download failed: %s", att_id, exc)
        att.status, att.error = Attachment.FAILED, str(exc)[:500]
        att.save(update_fields=["status", "error"])
    from core.realtime import bump
    bump(att.workspace_id)
    return att


def retry_pending():
    """Worker safety net: finish downloads interrupted by a restart; drop unsent uploads after a day."""
    cutoff = timezone.now() - timezone.timedelta(minutes=2)
    for att_id in Attachment.objects.filter(status=Attachment.PENDING, created_at__lt=cutoff,
                                            message__isnull=False).values_list("id", flat=True)[:50]:
        download(att_id)
    old = Attachment.objects.filter(message__isnull=True, created_at__lt=timezone.now() - timezone.timedelta(days=1))
    for att in old[:200]:
        att.file.delete(save=False)
        att.delete()


# ------------------------------------------------------------------ voice notes
def ffmpeg_path():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def convert(att, target):
    """Bytes of the attachment in another audio format ("ogg" = Opus voice note, "m4a" = AAC). Needs ffmpeg."""
    exe = ffmpeg_path()
    if not exe:
        raise ValueError("Converting voice notes needs ffmpeg (pip install imageio-ffmpeg).")
    args = {"ogg": ["-vn", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg"],
            "m4a": ["-vn", "-c:a", "aac", "-b:a", "64k", "-f", "ipod"],
            "mp3": ["-vn", "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3"]}[target]
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in"), os.path.join(tmp, f"out.{target}")
        with att.file.open("rb") as f, open(src, "wb") as out:
            shutil.copyfileobj(f, out)
        proc = subprocess.run([exe, "-y", "-loglevel", "error", "-i", src, *args, dst], capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise ValueError(f"Couldn't convert the audio: {proc.stderr.decode(errors='replace')[:200]}")
        with open(dst, "rb") as f:
            return f.read()


def normalize_voice(att):
    """Browsers record webm/opus; store voice notes as ogg/opus, which WhatsApp and Telegram play as voice messages."""
    if att.kind != Attachment.VOICE or att.mime == "audio/ogg" or not ffmpeg_path():
        return att
    try:
        data = convert(att, "ogg")
    except (ValueError, subprocess.TimeoutExpired) as exc:
        logger.warning("Voice conversion failed for %s: %s", att.id, exc)
        return att
    old = att.file.name
    att.file.storage.delete(old)
    return store_bytes(att, data, "audio/ogg", "voice-note.ogg")


def read_bytes(att):
    with att.file.open("rb") as f:
        return f.read()
