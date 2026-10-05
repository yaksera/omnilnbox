"""Discord bot connector.

Receiving: Discord delivers messages only over the Gateway (websocket), so run the
worker `python manage.py run_discord` which keeps one bot connection per channel.
Sending: plain REST call to /channels/{id}/messages.

Threads are Discord channel ids (a DM channel with a user, or a guild text channel
when `listen_guilds` is enabled).
"""
from .base import BaseProvider, Field, IncomingMessage

API = "https://discord.com/api/v10"


class DiscordProvider(BaseProvider):
    key = "discord"
    label = "Discord"
    category = "chat"
    color = "#5865F2"
    receive_mode = "gateway"
    fields = [
        Field("bot_token", "Bot token", type="password", secret=True,
              help="Discord Developer Portal → your app → Bot → Reset Token. Enable MESSAGE CONTENT intent."),
        Field("listen_guilds", "Also capture server channels?", type="select", default="no", options=["no", "yes"],
              help="'no' = only direct messages to the bot. 'yes' = also messages that mention the bot in servers."),
    ]
    setup_steps = [
        "Create an application at discord.com/developers → Bot, and turn on the MESSAGE CONTENT intent.",
        "Copy the bot token and invite the bot to your server (OAuth2 → URL generator → bot scope).",
        "Run the worker: python manage.py run_discord (keeps the Gateway connection open).",
    ]

    def _headers(self):
        return {"Authorization": f"Bot {self.cred('bot_token')}"}

    def verify(self):
        me = self.http("GET", f"{API}/users/@me", headers=self._headers())
        return {"bot": f"{me.get('username')}", "bot_id": me.get("id")}

    def to_incoming(self, message: dict):
        """Convert a raw Gateway MESSAGE_CREATE payload into an IncomingMessage."""
        author = message.get("author", {})
        is_bot_self = author.get("id") == self.channel.state.get("bot_id")
        is_dm = message.get("guild_id") is None
        if not is_dm and self.creds.get("listen_guilds") != "yes":
            return None
        if author.get("bot") and not is_bot_self:
            return None
        text = message.get("content", "")
        atts = [{"type": (a.get("content_type") or "file").split("/")[0], "mime": a.get("content_type", ""),
                 "url": a.get("url"), "name": a.get("filename")} for a in message.get("attachments", [])]
        from django.utils.dateparse import parse_datetime
        return IncomingMessage(
            external_thread_id=message["channel_id"],
            contact_external_id=author.get("id") if not is_bot_self else message["channel_id"],
            contact_name=author.get("global_name") or author.get("username", ""),
            contact_handle=f"@{author.get('username')}" if author.get("username") else "",
            external_message_id=message.get("id", ""),
            text=text, attachments=atts,
            sent_at=parse_datetime(message["timestamp"]) if message.get("timestamp") else None,
            direction="out" if is_bot_self else "in",
        )

    can_send_media = True

    def send_media(self, conversation, files, text=""):
        import json as _json
        from inbox.media import read_bytes
        upload = {f"files[{i}]": (a.name or "file", read_bytes(a), a.mime) for i, a in enumerate(files[:10])}
        data = self.http("POST", f"{API}/channels/{conversation.external_thread_id}/messages", headers=self._headers(),
                         data={"payload_json": _json.dumps({"content": (text or "")[:2000]})}, files=upload, timeout=120)
        return data.get("id", "")

    def send(self, conversation, text):
        data = self.http("POST", f"{API}/channels/{conversation.external_thread_id}/messages",
                         headers=self._headers(), json={"content": text[:2000]})
        return data.get("id", "")
