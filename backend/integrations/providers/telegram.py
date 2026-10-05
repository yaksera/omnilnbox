"""Telegram Bot API connector.

Customers message your bot; replies go out through the same bot.
Two receive modes:
  * webhook  - Telegram POSTs updates to /api/webhooks/<channel_id>/ (needs a public HTTPS URL)
  * polling  - the worker calls getUpdates (great for local development)
"""
import hmac
import json
from datetime import datetime, timezone

from .base import BaseProvider, Field, IncomingMessage, ProviderError

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramProvider(BaseProvider):
    key = "telegram"
    label = "Telegram"
    category = "chat"
    color = "#229ED9"
    default_receive_mode = "polling or webhook"
    fields = [
        Field("bot_token", "Bot token", type="password", secret=True, help="Create a bot with @BotFather and paste its token."),
        Field("mode", "Receive mode", type="select", default="polling", options=["polling", "webhook"],
              help="Use 'webhook' in production (requires PUBLIC_BASE_URL over HTTPS)."),
    ]
    setup_steps = [
        "Open Telegram and talk to @BotFather → /newbot.",
        "Copy the bot token and paste it here.",
        "Customers start a chat with your bot; their messages appear in the inbox.",
    ]

    @property
    def receive_mode(self):  # type: ignore[override]
        return "webhook" if self.creds.get("mode") == "webhook" else "polling"

    def _call(self, method, **payload):
        data = self.http("POST", API.format(token=self.cred("bot_token"), method=method), json=payload)
        if not data.get("ok", False):
            raise ProviderError(data.get("description", "Telegram API error"))
        return data["result"]

    def verify(self):
        me = self._call("getMe")
        return {"bot_username": me.get("username"), "bot_id": me.get("id")}

    def on_connect(self):
        if self.receive_mode == "webhook":
            self._call(
                "setWebhook", url=self.channel.webhook_url,
                secret_token=self.channel.webhook_secret, allowed_updates=["message", "edited_message"],
            )
            return {"webhook": self.channel.webhook_url}
        # polling mode: make sure no webhook blocks getUpdates
        self._call("deleteWebhook")
        return {}

    def validate_webhook(self, request):
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        return hmac.compare_digest(header, self.channel.webhook_secret)

    def _parse_update(self, update):
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return None
        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        text = msg.get("text") or msg.get("caption") or ""
        attachments = []
        for kind in ("photo", "document", "voice", "video", "video_note", "animation", "sticker", "audio"):
            if kind in msg:
                item = msg[kind][-1] if kind == "photo" else msg[kind]  # photos come in sizes: take the largest
                attachments.append({"type": kind, "file_id": item.get("file_id"), "name": item.get("file_name", ""),
                                    "mime": item.get("mime_type") or ("image/jpeg" if kind == "photo" else
                                                                     "audio/ogg" if kind == "voice" else "")})
                break  # Telegram sends one media item per message (animations also carry a "document")
        name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or chat.get("title", "")
        return IncomingMessage(
            external_thread_id=str(chat.get("id")),
            contact_external_id=str(sender.get("id", chat.get("id"))),
            contact_name=name,
            contact_handle=f"@{sender['username']}" if sender.get("username") else "",
            external_message_id=str(msg.get("message_id")),
            text=text,
            attachments=attachments,
            sent_at=datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc) if msg.get("date") else None,
        )

    def parse_webhook(self, request):
        try:
            update = json.loads(request.body or b"{}")
        except ValueError:
            return []
        item = self._parse_update(update)
        return [item] if item else []

    def poll(self):
        offset = self.channel.state.get("tg_offset")
        payload = {"timeout": 0, "allowed_updates": ["message", "edited_message"]}
        if offset:
            payload["offset"] = offset
        updates = self._call("getUpdates", **payload)
        results = []
        for update in updates:
            self.channel.state["tg_offset"] = update["update_id"] + 1
            item = self._parse_update(update)
            if item:
                results.append(item)
        return results

    def send(self, conversation, text):
        result = self._call("sendMessage", chat_id=conversation.external_thread_id, text=text)
        return str(result.get("message_id", ""))

    can_send_media = True

    def fetch_attachment(self, source):
        from inbox.media import download_url
        info = self._call("getFile", file_id=source.get("file_id", ""))
        url = f"https://api.telegram.org/file/bot{self.cred('bot_token')}/{info.get('file_path', '')}"
        data, mime, _ = download_url(url)
        return data, mime, (info.get("file_path") or "").rsplit("/", 1)[-1]

    def send_media(self, conversation, files, text=""):
        from inbox.media import read_bytes
        caption, last = (text or "").strip(), ""
        for att in files:
            method, field = {"image": ("sendPhoto", "photo"), "video": ("sendVideo", "video"),
                             "audio": ("sendAudio", "audio"), "sticker": ("sendPhoto", "photo"),
                             "voice": ("sendVoice", "voice") if att.mime == "audio/ogg" else ("sendAudio", "audio"),
                             }.get(att.kind, ("sendDocument", "document"))
            if method == "sendPhoto" and att.mime not in ("image/jpeg", "image/png", "image/webp"):
                method, field = "sendDocument", "document"
            form = {"chat_id": conversation.external_thread_id}
            if caption:
                form["caption"], caption = caption[:1024], ""
            data = self.http("POST", API.format(token=self.cred("bot_token"), method=method), data=form, timeout=120,
                             files={field: (att.name or "file", read_bytes(att), att.mime)})
            if not data.get("ok", False):
                raise ProviderError(data.get("description", "Telegram API error"))
            last = str(data["result"].get("message_id", ""))
        return last
