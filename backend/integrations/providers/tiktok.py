"""TikTok Business Messaging API connector (BETA).

TikTok's Business Messaging API is gated: your developer app must be approved for
Business Messaging and it is only available in some regions. The API is authenticated
with the `Access-Token` header against https://business-api.tiktok.com/open_api/v1.3.

Because TikTok changes this API frequently and exact paths depend on your approval
tier, the send path is configurable and the webhook parser is defensive. Check the
official reference (business-api.tiktok.com/portal/docs/business-messaging/v1.3) and
adjust `send_path` / `_extract_messages` if your payloads differ.
"""
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone

from .base import BaseProvider, Field, IncomingMessage, ProviderError

BASE = "https://business-api.tiktok.com/open_api/v1.3"
SAFE_PATH = re.compile(r"^/[a-z0-9_/]{1,100}$")


class TikTokProvider(BaseProvider):
    key = "tiktok"
    label = "TikTok"
    category = "social"
    color = "#111111"
    beta = True
    fields = [
        Field("access_token", "Business access token", type="password", secret=True,
              help="Token for the TikTok Business account (Business Messaging scope)."),
        Field("business_id", "Business ID", help="The TikTok business account ID (open_id)."),
        Field("app_secret", "App secret", type="password", secret=True,
              help="Used to verify webhook signatures (required)."),
        Field("send_path", "Send message path", required=False, default="/business/message/send/",
              help="Relative to /open_api/v1.3. Adjust if your API version differs."),
    ]
    setup_steps = [
        "Apply for Business Messaging API access in the TikTok API for Business portal (approval + region limits apply).",
        "Authorize your TikTok Business account and copy its access token and business ID.",
        "Create a Business Messaging webhook configuration pointing to this channel's webhook URL.",
    ]

    def _headers(self):
        return {"Access-Token": self.cred("access_token"), "Content-Type": "application/json"}

    def verify(self):
        data = self.http("GET", f"{BASE}/business/get/", headers=self._headers(),
                         params={"business_id": self.cred("business_id"), "fields": json.dumps(["username", "display_name"])})
        info = data.get("data", {}) if isinstance(data, dict) else {}
        return {"username": info.get("username"), "display_name": info.get("display_name")}

    def validate_webhook(self, request):
        secret = self.creds.get("app_secret")
        if not secret:
            return False  # fail closed: never accept unsigned webhooks
        signature = request.headers.get("TikTok-Signature", "")
        # Header format: "t=<timestamp>,s=<hex hmac>" signed over "<timestamp>.<body>"
        parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p)
        if not parts.get("t") or not parts.get("s"):
            return False
        try:
            if abs(time.time() - int(parts["t"])) > 300:
                return False  # replay protection: reject signatures older than 5 minutes
        except ValueError:
            return False
        payload = f"{parts['t']}.".encode() + request.body
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["s"])

    @staticmethod
    def _extract_messages(body):
        """Yield message dicts from the known/likely webhook shapes."""
        content = body.get("content", body)
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except ValueError:
                content = {}
        if isinstance(content, dict):
            if "messages" in content:
                yield from content["messages"]
            elif content.get("message") or content.get("text"):
                yield content

    def parse_webhook(self, request):
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            return []
        results = []
        for m in self._extract_messages(body):
            msg = m.get("message", m)
            sender = m.get("sender") or m.get("from") or {}
            sender_id = sender.get("id") if isinstance(sender, dict) else str(sender)
            conv_id = m.get("conversation_id") or sender_id
            if not conv_id:
                continue
            if sender_id and sender_id == self.creds.get("business_id"):
                direction = "out"
            else:
                direction = "in"
            text = (msg.get("text") or {}).get("body") if isinstance(msg.get("text"), dict) else msg.get("text")
            ts = m.get("timestamp") or m.get("create_time")
            results.append(IncomingMessage(
                external_thread_id=str(conv_id),
                contact_external_id=str(sender_id or conv_id),
                contact_name=(sender.get("display_name") or sender.get("username") or "") if isinstance(sender, dict) else "",
                contact_handle=f"@{sender['username']}" if isinstance(sender, dict) and sender.get("username") else "",
                external_message_id=str(m.get("message_id") or msg.get("message_id") or ""),
                text=text or f"[{msg.get('message_type', 'message')}]",
                sent_at=datetime.fromtimestamp(int(ts) / (1000 if int(ts) > 10**12 else 1), tz=timezone.utc) if ts else None,
                direction=direction,
            ))
        return results

    def send(self, conversation, text):
        path = self.creds.get("send_path") or "/business/message/send/"
        if not SAFE_PATH.match(path):
            raise ProviderError("Invalid send path.")
        data = self.http("POST", f"{BASE}{path}", headers=self._headers(), json={
            "business_id": self.cred("business_id"),
            "recipient_type": "CONVERSATION",
            "recipient": conversation.external_thread_id,
            "message_type": "TEXT",
            "text": {"body": text},
        })
        if isinstance(data, dict) and data.get("code") not in (0, None):
            raise ProviderError(f"TikTok error {data.get('code')}: {data.get('message')}")
        return str((data.get("data") or {}).get("message_id", "")) if isinstance(data, dict) else ""
