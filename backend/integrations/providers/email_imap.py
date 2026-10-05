"""Email over IMAP (receive) + SMTP (send). Used for Gmail, Zoho Mail and any other mailbox.

Gmail:  enable 2-Step Verification and create an App Password (myaccount.google.com/apppasswords).
Zoho:   Settings → Mail Accounts → IMAP Access ON, then create an app-specific password.

Conversations are grouped by email thread (root Message-ID from References/In-Reply-To),
so a whole email thread shows up as one conversation.
"""
import email
import email.policy
import email.utils
import imaplib
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage

from core.netguard import UnsafeHostError, assert_public_host

from .base import BaseProvider, Field, IncomingMessage, ProviderError

PRESETS = {
    "gmail": {"imap_host": "imap.gmail.com", "imap_port": 993, "smtp_host": "smtp.gmail.com", "smtp_port": 465},
    "zoho": {"imap_host": "imap.zoho.com", "imap_port": 993, "smtp_host": "smtp.zoho.com", "smtp_port": 465},
    "imap": {"imap_host": "", "imap_port": 993, "smtp_host": "", "smtp_port": 465},
}

MAX_FETCH = 50
FIRST_SYNC_DAYS = 7


def _decode(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _html_to_text(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", html)
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_quoted(text):
    """Drop the quoted history of a reply so the inbox shows only the new part."""
    lines, out = text.splitlines(), []
    for line in lines:
        if re.match(r"^On .+wrote:\s*$", line) or line.startswith(">") or line.strip() == "-----Original Message-----":
            break
        out.append(line)
    cleaned = "\n".join(out).strip()
    return cleaned or text.strip()


def extract_body(msg):
    text, html, attachments = "", "", []
    if msg.is_multipart():
        for part in msg.walk():
            disp = (part.get("Content-Disposition") or "").lower()
            ctype = part.get_content_type()
            if "attachment" in disp or (part.get_filename() and ctype not in ("text/plain", "text/html")) or (
                    "inline" in disp and ctype.startswith("image/")):
                attachments.append({"type": ctype, "mime": ctype, "name": _decode(part.get_filename() or "file"),
                                    "data": part.get_payload(decode=True) or b""})
                continue
            if ctype == "text/plain" and not text:
                text = part.get_content() if hasattr(part, "get_content") else part.get_payload(decode=True).decode(errors="replace")
            elif ctype == "text/html" and not html:
                html = part.get_content() if hasattr(part, "get_content") else part.get_payload(decode=True).decode(errors="replace")
    else:
        payload = msg.get_content() if hasattr(msg, "get_content") else msg.get_payload(decode=True).decode(errors="replace")
        if msg.get_content_type() == "text/html":
            html = payload
        else:
            text = payload
    if not text and html:
        text = _html_to_text(html)
    return _strip_quoted(text or ""), html, attachments


def thread_root(msg):
    refs = (msg.get("References") or "").split()
    if refs:
        return refs[0].strip()
    irt = (msg.get("In-Reply-To") or "").strip()
    if irt:
        return irt.split()[0]
    return (msg.get("Message-ID") or "").strip()


class ImapEmailProvider(BaseProvider):
    key = "imap"
    label = "Email (IMAP/SMTP)"
    category = "email"
    color = "#0EA5E9"
    receive_mode = "polling"
    fields = [
        Field("email", "Email address"),
        Field("password", "App password", type="password", secret=True),
        Field("imap_host", "IMAP host"),
        Field("imap_port", "IMAP port", type="number", default="993"),
        Field("smtp_host", "SMTP host"),
        Field("smtp_port", "SMTP port", type="number", default="465", help="465 = SSL, 587 = STARTTLS"),
    ]
    setup_steps = ["Enable IMAP in your mailbox and create an app password.", "Enter the IMAP/SMTP server details."]

    def _setting(self, name):
        value = self.creds.get(name) or PRESETS.get(self.key, {}).get(name)
        if value in (None, ""):
            raise ProviderError(f"Missing setting: {name}")
        return value

    # ---- connections -------------------------------------------------
    def _guard(self, host, port):
        try:
            assert_public_host(host, int(port))
        except (UnsafeHostError, ValueError) as exc:
            raise ProviderError(str(exc)) from exc

    def _imap(self):
        host, port = self._setting("imap_host"), int(self._setting("imap_port"))
        self._guard(host, port)
        try:
            conn = imaplib.IMAP4_SSL(host, port, timeout=30)
            conn.login(self.cred("email"), self.cred("password"))
            return conn
        except imaplib.IMAP4.error as exc:
            raise ProviderError(f"IMAP login failed: {exc}") from exc
        except OSError as exc:
            raise ProviderError(f"Cannot reach IMAP server: {exc}") from exc

    def _smtp(self):
        host, port = self._setting("smtp_host"), int(self._setting("smtp_port"))
        self._guard(host, port)
        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30)
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                server.starttls(context=ssl.create_default_context())
            server.login(self.cred("email"), self.cred("password"))
            return server
        except smtplib.SMTPException as exc:
            raise ProviderError(f"SMTP error: {exc}") from exc
        except OSError as exc:
            raise ProviderError(f"Cannot reach SMTP server: {exc}") from exc

    def verify(self):
        conn = self._imap()
        conn.logout()
        self._smtp().quit()
        return {"email": self.creds.get("email")}

    # ---- receiving ---------------------------------------------------
    def poll(self):
        own = self.cred("email").lower()
        conn = self._imap()
        try:
            conn.select("INBOX", readonly=True)
            last_uid = int(self.channel.state.get("last_uid", 0))
            if last_uid:
                typ, data = conn.uid("search", None, f"UID {last_uid + 1}:*")
            else:
                since = (datetime.now(timezone.utc) - timedelta(days=FIRST_SYNC_DAYS)).strftime("%d-%b-%Y")
                typ, data = conn.uid("search", None, f"SINCE {since}")
            uids = [int(u) for u in (data[0] or b"").split() if int(u) > last_uid][-MAX_FETCH:]
            results = []
            for uid in uids:
                typ, fetched = conn.uid("fetch", str(uid), "(RFC822)")
                if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    continue
                msg = email.message_from_bytes(fetched[0][1], policy=email.policy.default)
                self.channel.state["last_uid"] = max(uid, int(self.channel.state.get("last_uid", 0)))
                from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
                from_addr = from_addr.lower()
                if from_addr == own:
                    continue  # our own sent mail copied into INBOX
                text, html, attachments = extract_body(msg)
                message_id = (msg.get("Message-ID") or "").strip()
                subject = _decode(msg.get("Subject", ""))
                try:
                    sent_at = email.utils.parsedate_to_datetime(msg.get("Date"))
                    if sent_at.tzinfo is None:
                        sent_at = sent_at.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    sent_at = None
                root = thread_root(msg) or f"uid-{uid}"
                results.append(IncomingMessage(
                    external_thread_id=root,
                    contact_external_id=from_addr,
                    contact_name=_decode(from_name),
                    contact_handle=from_addr,
                    external_message_id=message_id or f"uid-{uid}",
                    text=text, html=html[:200000], attachments=attachments,
                    subject=subject, sent_at=sent_at,
                    thread_meta={
                        "reply_to": from_addr,
                        "last_message_id": message_id,
                        "references": ((msg.get("References") or "") + " " + message_id).strip(),
                        "subject": subject,
                    },
                ))
            return results
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass

    # ---- sending -----------------------------------------------------
    def send(self, conversation, text):
        meta = conversation.meta or {}
        to_addr = meta.get("reply_to") or conversation.contact.handle or conversation.contact.external_id
        subject = meta.get("subject") or conversation.subject or "(no subject)"
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        msg = EmailMessage()
        msg["From"] = self.cred("email")
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=False)
        domain = self.cred("email").split("@")[-1]
        msg["Message-ID"] = email.utils.make_msgid(domain=domain)
        if meta.get("last_message_id"):
            msg["In-Reply-To"] = meta["last_message_id"]
            msg["References"] = meta.get("references") or meta["last_message_id"]
        msg.set_content(text or " ")
        from inbox.media import read_bytes
        for att in getattr(self, "_outgoing_files", []) or []:
            maintype, _, subtype = (att.mime or "application/octet-stream").partition("/")
            msg.add_attachment(read_bytes(att), maintype=maintype, subtype=subtype or "octet-stream",
                               filename=att.name or "file")
        server = self._smtp()
        try:
            server.send_message(msg)
        finally:
            server.quit()
        return msg["Message-ID"]

    can_send_media = True

    def send_media(self, conversation, files, text=""):
        """Reply by email with the files attached."""
        self._outgoing_files = files
        try:
            return self.send(conversation, text)
        finally:
            self._outgoing_files = []


class GmailProvider(ImapEmailProvider):
    key = "gmail"
    label = "Gmail"
    color = "#EA4335"
    fields = [
        Field("email", "Gmail address"),
        Field("password", "App password", type="password", secret=True,
              help="Google Account → Security → 2-Step Verification → App passwords."),
    ]
    setup_steps = [
        "Turn on 2-Step Verification for the Google account.",
        "Create an App Password at myaccount.google.com/apppasswords.",
        "Paste the Gmail address and the 16-character app password here.",
    ]


class ZohoProvider(ImapEmailProvider):
    key = "zoho"
    label = "Zoho Mail"
    color = "#F0B31C"
    fields = [
        Field("email", "Zoho email address"),
        Field("password", "App-specific password", type="password", secret=True,
              help="Zoho Accounts → Security → App Passwords."),
        Field("region", "Data center", type="select", default="com", options=["com", "eu", "in", "com.au", "jp"],
              help="Match the domain you log in at (zoho.com, zoho.eu, zoho.in...)."),
    ]
    setup_steps = [
        "In Zoho Mail → Settings → Mail Accounts → IMAP Access, enable IMAP.",
        "Create an app-specific password in Zoho Accounts → Security.",
        "Pick your data center region and paste the credentials here.",
    ]

    def _setting(self, name):
        region = self.creds.get("region", "com")
        if name == "imap_host":
            return f"imap.zoho.{region}"
        if name == "smtp_host":
            return f"smtp.zoho.{region}"
        return super()._setting(name)
