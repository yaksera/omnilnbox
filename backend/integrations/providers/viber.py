"""Viber (Rakuten Viber REST Bot API).

Since February 2024 Viber creates new bots only on commercial terms: apply for a bot at
https://partners.viber.com, then paste its authentication token here. Messages arrive by webhook
(Viber requires a public HTTPS URL) and are signed with X-Viber-Content-Signature.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone

from .base import BaseProvider, Field, IncomingMessage, ProviderError

API = "https://chatapi.viber.com/pa/"


class ViberProvider(BaseProvider):
    key = "viber"
    label = "Viber"
    category = "chat"
    color = "#7360F2"
    receive_mode = "webhook"
    fields = [
        Field("auth_token", "Bot authentication token", type="password", secret=True,
              help="Viber Partners / Admin Panel → your bot → Authentication token."),
        Field("sender_name", "Sender name", required=False, help="Name shown on replies (max 28 characters). Defaults to the bot name."),
    ]
    setup_steps = [
        "Apply for a Viber bot (commercial account) at partners.viber.com and wait for approval.",
        "Copy the bot's authentication token and paste it here.",
        "Make sure PUBLIC_BASE_URL is a public HTTPS address; OmniInbox registers the webhook for you.",
        "Customers find your bot in Viber (or via its link / QR code) and start chatting.",
    ]

    def _call(self, method, payload=None):
        data = self.http("POST", API + method, json=payload or {},
                         headers={"X-Viber-Auth-Token": self.cred("auth_token")})
        if data.get("status", 0) != 0:
            raise ProviderError(f"Viber: {data.get('status_message', 'error')} (status {data.get('status')})")
        return data

    def verify(self):
        info = self._call("get_account_info")
        if not self.creds.get("sender_name"):
            self.creds["sender_name"] = (info.get("name") or "")[:28]
            self.channel.credentials = self.creds
        return {"bot": info.get("name"), "uri": info.get("uri"), "subscribers": info.get("subscribers_count")}

    def on_connect(self):
        self._call("set_webhook", {"url": self.channel.webhook_url, "send_name": True, "send_photo": True,
                                   "event_types": ["delivered", "seen", "failed", "subscribed", "unsubscribed",
                                                   "conversation_started"]})
        return {"webhook": self.channel.webhook_url}

    def validate_webhook(self, request):
        sig = request.headers.get("X-Viber-Content-Signature", "")
        token = self.creds.get("auth_token", "")
        expected = hmac.new(token.encode(), request.body, hashlib.sha256).hexdigest()
        return bool(token) and hmac.compare_digest(sig, expected)

    def parse_webhook(self, request):
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            return []
        if body.get("event") != "message":
            return []  # webhook check, delivered/seen receipts, (un)subscribed
        sender, msg = body.get("sender") or {}, body.get("message") or {}
        mtype = msg.get("type", "text")
        text = msg.get("text") or ""
        atts = []
        if mtype in ("picture", "video", "file", "sticker"):
            atts = [{"type": mtype, "url": msg.get("media"), "name": msg.get("file_name") or ""}]
        elif mtype == "location":
            loc = msg.get("location") or {}
            text = f"📍 https://maps.google.com/?q={loc.get('lat')},{loc.get('lon')}"
        elif mtype == "contact":
            c = msg.get("contact") or {}
            text = f"📇 {c.get('name', '')} {c.get('phone_number', '')}".strip()
        ts = body.get("timestamp")
        return [IncomingMessage(
            external_thread_id=sender.get("id", ""), contact_external_id=sender.get("id", ""),
            contact_name=sender.get("name", ""), contact_avatar=sender.get("avatar", "") or "",
            external_message_id=str(body.get("message_token", "")), text=text, attachments=atts,
            sent_at=datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts else None,
        )]

    can_send_media = True

    def send_media(self, conversation, files, text=""):
        """Viber downloads media from a URL, so PUBLIC_BASE_URL must be reachable from the internet."""
        from inbox import media
        sender = {"name": (self.creds.get("sender_name") or self.channel.name)[:28]}
        caption, last = (text or "").strip(), ""
        for att in files:
            base = {"receiver": conversation.external_thread_id, "min_api_version": 1, "sender": sender}
            url = media.public_url(att)
            if att.kind in ("image", "sticker") and att.mime in ("image/jpeg", "image/png") and att.size <= 1024 * 1024:
                body = {**base, "type": "picture", "media": url, "text": caption[:120]}
                caption = caption[120:] if len(caption) > 120 else ""
            elif att.kind == "video" and att.mime == "video/mp4":
                body = {**base, "type": "video", "media": url, "size": att.size}
            else:
                body = {**base, "type": "file", "media": url, "size": att.size, "file_name": (att.name or "file")[:255]}
            last = str(self._call("send_message", body).get("message_token", ""))
        if caption:
            last = self.send(conversation, caption)
        return last

    def send(self, conversation, text):
        data = self._call("send_message", {
            "receiver": conversation.external_thread_id, "min_api_version": 1, "type": "text", "text": text[:7000],
            "sender": {"name": (self.creds.get("sender_name") or self.channel.name)[:28]},
        })
        return str(data.get("message_token", ""))
