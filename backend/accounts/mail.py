"""Transactional emails (plain text + simple HTML)."""
import logging
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def send(to, subject, lines, button=None):
    """lines: paragraphs of text. button: (label, url). Returns True if handed to the mail backend."""
    text = "\n\n".join(lines) + (f"\n\n{button[0]}: {button[1]}" if button else "") + "\n\n— OmniInbox"
    btn = (f'<p style="margin:24px 0"><a href="{escape(button[1])}" style="background:#4f46e5;color:#fff;'
           f'padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600">{escape(button[0])}</a></p>'
           f'<p style="color:#64748b;font-size:12px">Or open this link: {escape(button[1])}</p>') if button else ""
    html = (f'<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:520px;color:#0f172a">'
            f'<p style="font-weight:700;font-size:18px">OmniInbox</p>'
            + "".join(f"<p>{escape(p)}</p>" for p in lines) + btn + "</div>")
    try:
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to] if isinstance(to, str) else to)
        msg.attach_alternative(html, "text/html")
        msg.send()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Email to %s failed", to)
        return False
