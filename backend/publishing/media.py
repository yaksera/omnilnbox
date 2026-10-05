"""Media validation and signed, expiring links.

Uploaded files are never exposed at a guessable static URL. Instagram and Facebook
need to *fetch* the media from a public URL, so we hand them a signed link that
expires; the UI gets its own short-lived preview link.
"""
import logging
import os
import re
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.core import signing

SALT = "omniinbox.publishing.media"

IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png"}
VIDEO_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov"}
MAX_IMAGE = 8 * 1024 * 1024          # Instagram / Facebook photo limit
MAX_VIDEO = 500 * 1024 * 1024


def sniff(head: bytes):
    """Detect the real file type from its first bytes (don't trust the browser's Content-Type)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    return None


def signed_token(asset_id, purpose="public"):
    return signing.dumps({"a": str(asset_id), "p": purpose}, salt=SALT, compress=True)


def read_token(token, max_age):
    data = signing.loads(token, salt=SALT, max_age=max_age)
    return data["a"]


def public_url(asset, hours=24):
    """URL a platform can fetch (valid `hours`)."""
    return f"{settings.PUBLIC_BASE_URL}/api/publishing/files/{signed_token(asset.id)}/"


def preview_path(asset):
    """Relative path the web app can load through its /backend proxy (checked for 1 hour)."""
    return f"/backend/publishing/files/{signed_token(asset.id, 'preview')}/"


# ------------------------------------------------------------------ video facts (ffmpeg)
logger = logging.getLogger(__name__)


def _ffmpeg():
    from inbox.media import ffmpeg_path
    return ffmpeg_path()


class _LocalCopy:
    """A real file path for ffmpeg (storage may not be the local disk)."""

    def __init__(self, asset):
        self.asset, self.dir = asset, None

    def __enter__(self):
        try:
            return self.asset.file.path
        except (NotImplementedError, AttributeError, ValueError):
            self.dir = tempfile.mkdtemp()
            path = os.path.join(self.dir, "in")
            with self.asset.file.open("rb") as src, open(path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return path

    def __exit__(self, *exc):
        if self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)


def probe(asset):
    """{"width", "height", "duration"} of a video (or image), read with ffmpeg. {} when ffmpeg isn't available."""
    exe = _ffmpeg()
    if not exe:
        return {}
    with _LocalCopy(asset) as path:
        try:
            proc = subprocess.run([exe, "-hide_banner", "-i", path], capture_output=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            return {}
    out = proc.stderr.decode(errors="replace")
    info = {}
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if m:
        info["duration"] = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 2)
    m = re.search(r"Video: [^\n]*?(\d{2,5})x(\d{2,5})", out)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        # phone videos are often stored sideways with a rotation flag
        rot = re.search(r"rotation of (-?\d+(?:\.\d+)?)|rotate\s*:\s*(-?\d+)", out)
        if rot and abs(round(float(rot.group(1) or rot.group(2)))) % 180 == 90:
            w, h = h, w
        info.update(width=w, height=h)
    return info


def extract_audio(asset, max_seconds=600):
    """MP3 bytes of the video's sound (mono, small), or None."""
    exe = _ffmpeg()
    if not exe:
        return None
    with _LocalCopy(asset) as path, tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "a.mp3")
        proc = subprocess.run([exe, "-y", "-loglevel", "error", "-i", path, "-t", str(max_seconds), "-vn", "-ac", "1",
                                "-ar", "16000", "-b:a", "32k", dst], capture_output=True, timeout=300)
        if proc.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 1000:
            return None  # silent video / no audio track
        with open(dst, "rb") as f:
            return f.read()


def extract_frames(asset, count=4, duration=None):
    """JPEG bytes of a few frames spread over the video (512 px wide), for the AI to look at."""
    exe = _ffmpeg()
    if not exe:
        return []
    duration = duration or float(asset.duration or 0) or 10.0
    frames = []
    with _LocalCopy(asset) as path, tempfile.TemporaryDirectory() as tmp:
        for i in range(count):
            at = max(0.0, duration * (0.1 + 0.8 * i / max(1, count - 1)))
            dst = os.path.join(tmp, f"f{i}.jpg")
            proc = subprocess.run([exe, "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", path, "-frames:v", "1",
                                    "-vf", "scale=512:-2", "-q:v", "5", dst], capture_output=True, timeout=60)
            if proc.returncode == 0 and os.path.exists(dst):
                with open(dst, "rb") as f:
                    frames.append(f.read())
    return frames
