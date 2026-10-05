"""Meta platform connectors: WhatsApp Cloud API, Messenger and Instagram Messaging.

All three use the same webhook handshake (hub.challenge) and payload signature
(X-Hub-Signature-256 = HMAC-SHA256(app_secret, raw body)).
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone

from django.http import HttpResponse
from django.utils.dateparse import parse_datetime

from inbox.models import Contact

from .base import BaseProvider, Field, IncomingMessage, ProviderError

GRAPH_VERSION = "v21.0"
THREAD_CONTROLLED_ELSEWHERE = 2018300  # "another app is controlling this thread"
ROUTING_DISABLED = 2018464  # take_thread_control needs Conversation Routing
NO_CONTROL_PERMISSION = 1893034  # the Page hasn't given this app "conversation control"
PAGE_FIELDS = "messages,message_echoes,messaging_postbacks,standby,feed"
ROUTING_HELP = ("Another app (Meta Business Suite inbox, Meta Business AI or a chatbot) controls this conversation. "
                "Fix once per Page: Meta Business Suite -> Settings -> Advanced messaging (Conversation routing) -> "
                "set OmniInbox's app as the app that controls conversations (or give it 'Conversation control'), and "
                "turn off Business AI / automated responses. Messages still arrive in OmniInbox meanwhile.")


def _ts(value, millis=False):
    if not value:
        return None
    value = int(value)
    return datetime.fromtimestamp(value / 1000 if millis else value, tz=timezone.utc)


def _wa_attachments(m, mtype):
    if mtype not in ("image", "video", "document", "audio", "sticker"):
        return []
    media = m.get(mtype, {})
    kind = "voice" if mtype == "audio" and media.get("voice") else mtype
    return [{"type": kind, "id": media.get("id"), "mime": media.get("mime_type", ""), "name": media.get("filename", "")}]


# WhatsApp Cloud API accepted formats (anything else goes as a document)
WA_TYPES = {"image": {"image/jpeg", "image/png"}, "video": {"video/mp4", "video/3gpp"},
            "audio": {"audio/ogg", "audio/mpeg", "audio/aac", "audio/mp4", "audio/amr"}}


class MetaBaseProvider(BaseProvider):
    graph_host = "https://graph.facebook.com"

    common_fields = [
        Field("app_secret", "App secret", type="password", secret=True,
              help="Meta app → Settings → Basic. Used to verify webhook signatures."),
        Field("verify_token", "Webhook verify token", required=False,
              help="Any random string. Paste the same value in the Meta webhook settings. Defaults to the channel's webhook secret."),
    ]

    def graph(self, method, path, token, **kwargs):
        url = f"{self.graph_host}/{GRAPH_VERSION}/{path.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"  # keep tokens out of URLs/proxy logs
        secret = self.creds.get("app_secret")
        if secret:
            # appsecret_proof: a stolen token alone can't be used against our app
            # (enable "Require App Secret" in the Meta app's Advanced settings to enforce it)
            params = kwargs.pop("params", None) or {}
            params["appsecret_proof"] = hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
            kwargs["params"] = params
        try:
            return self.http(method, url, headers=headers, **kwargs)
        except ProviderError as exc:
            err = exc.detail.get("error") or {}
            if err.get("code") == 190:  # OAuthException: expired / invalid / revoked token
                raise ProviderError(
                    "The Meta access token has expired or was revoked. In Meta Business Settings -> System users, "
                    "generate a new token with 'Token expiration: Never', then paste it in Channels -> Edit "
                    f"(replace the dots in the token field) and Save. [Meta: {err.get('message', '')[:120]}]",
                    status=exc.status, detail=exc.detail,
                ) from exc
            raise

    @property
    def verify_token(self):
        return self.creds.get("verify_token") or self.channel.webhook_secret

    def webhook_challenge(self, request):
        if request.GET.get("hub.mode") == "subscribe":
            if request.GET.get("hub.verify_token") == self.verify_token:
                return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
            return HttpResponse("verify token mismatch", status=403)
        return None

    def validate_webhook(self, request):
        secret = self.creds.get("app_secret")
        if not secret:
            return False
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def _body(request):
        try:
            return json.loads(request.body or b"{}")
        except ValueError:
            return {}


class WhatsAppProvider(MetaBaseProvider):
    key = "whatsapp"
    label = "WhatsApp"
    category = "chat"
    color = "#25D366"
    fields = [
        Field("access_token", "Permanent access token", type="password", secret=True,
              help="System-user token with whatsapp_business_messaging permission."),
        Field("phone_number_id", "Phone number ID", help="WhatsApp Manager → API Setup."),
        Field("business_account_id", "WhatsApp Business Account ID", required=False,
              help="Needed for broadcasts (message templates). WhatsApp Manager → Account tools / API Setup."),
        *MetaBaseProvider.common_fields,
    ]
    setup_steps = [
        "Create a Meta app with the WhatsApp product (developers.facebook.com).",
        "Copy the Phone number ID and a permanent System User access token.",
        "In WhatsApp → Configuration set the Callback URL to this channel's webhook URL and the verify token.",
        "Subscribe to the 'messages' webhook field.",
    ]

    def verify(self):
        info = self.graph("GET", self.cred("phone_number_id"), self.cred("access_token"),
                          params={"fields": "display_phone_number,verified_name"})
        return {"phone": info.get("display_phone_number"), "name": info.get("verified_name")}

    def parse_webhook(self, request):
        body = self._body(request)
        results = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("metadata", {}).get("phone_number_id") not in (None, self.creds.get("phone_number_id")):
                    continue
                names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
                for m in value.get("messages", []):
                    mtype = m.get("type")
                    if mtype == "text":
                        text = m.get("text", {}).get("body", "")
                    elif mtype in ("image", "video", "document", "audio", "sticker"):
                        text = m.get(mtype, {}).get("caption") or f"[{mtype}]"
                    elif mtype == "interactive":
                        inter = m.get("interactive", {})
                        text = (inter.get("button_reply") or inter.get("list_reply") or {}).get("title", "[interactive]")
                    elif mtype == "button":
                        text = m.get("button", {}).get("text", "[button]")
                    else:
                        text = f"[{mtype}]"
                    wa_id = m.get("from")
                    results.append(IncomingMessage(
                        external_thread_id=wa_id, contact_external_id=wa_id,
                        contact_name=names.get(wa_id, ""), contact_handle=f"+{wa_id}",
                        external_message_id=m.get("id", ""), text=text,
                        attachments=_wa_attachments(m, mtype),
                        sent_at=_ts(m.get("timestamp")),
                    ))
        return results

    def templates(self):
        """Approved message templates (for broadcasts outside the 24-hour window)."""
        waba = self.creds.get("business_account_id")
        if not waba:
            raise ProviderError("Add the WhatsApp Business Account ID to this channel (Channels → Edit) to use templates.")
        data = self.graph("GET", f"{waba}/message_templates", self.cred("access_token"),
                          params={"fields": "name,language,status,category,components", "limit": "200"})
        out = []
        for t in data.get("data", []):
            body = next((c.get("text", "") for c in t.get("components", []) if c.get("type") == "BODY"), "")
            has_media_header = any(c.get("type") == "HEADER" and c.get("format") in ("IMAGE", "VIDEO", "DOCUMENT")
                                   for c in t.get("components", []))
            out.append({"name": t.get("name"), "language": t.get("language"), "status": t.get("status"),
                        "category": t.get("category"), "body": body, "variables": body.count("{{"),
                        "media_header": has_media_header})
        return out

    def send_template(self, conversation, name, language, params):
        component = [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:1000]} for p in params]}] if params else []
        data = self.graph("POST", f"{self.cred('phone_number_id')}/messages", self.cred("access_token"), json={
            "messaging_product": "whatsapp", "to": conversation.external_thread_id, "type": "template",
            "template": {"name": name, "language": {"code": language}, "components": component},
        })
        return (data.get("messages") or [{}])[0].get("id", "")

    def send(self, conversation, text):
        data = self.graph("POST", f"{self.cred('phone_number_id')}/messages", self.cred("access_token"), json={
            "messaging_product": "whatsapp", "recipient_type": "individual",
            "to": conversation.external_thread_id, "type": "text", "text": {"body": text},
        })
        messages = data.get("messages") or [{}]
        return messages[0].get("id", "")

    can_send_media = True

    def fetch_attachment(self, source):
        from inbox.media import download_url
        token = self.cred("access_token")
        info = self.graph("GET", str(source.get("id", "")), token)
        if not info.get("url"):
            raise ProviderError("WhatsApp didn't return a download link (media expire after 30 days).")
        data, mime, name = download_url(info["url"], headers={"Authorization": f"Bearer {token}"})
        return data, info.get("mime_type") or mime, name

    def _upload(self, att):
        from inbox.media import read_bytes
        data = self.graph("POST", f"{self.cred('phone_number_id')}/media", self.cred("access_token"),
                          data={"messaging_product": "whatsapp", "type": att.mime},
                          files={"file": (att.name or "file", read_bytes(att), att.mime)}, timeout=120)
        return data.get("id")

    def send_media(self, conversation, files, text=""):
        last, caption = "", (text or "").strip()
        for att in files:
            wa_type = next((t for t, mimes in WA_TYPES.items() if att.mime in mimes), "document")
            media = {"id": self._upload(att)}
            if wa_type == "document":
                media["filename"] = att.name or "file"
            if caption and wa_type != "audio":
                media["caption"], caption = caption[:1024], ""
            data = self.graph("POST", f"{self.cred('phone_number_id')}/messages", self.cred("access_token"), json={
                "messaging_product": "whatsapp", "recipient_type": "individual",
                "to": conversation.external_thread_id, "type": wa_type, wa_type: media})
            last = (data.get("messages") or [{}])[0].get("id", "")
        if caption:  # e.g. text sent together with a voice note
            last = self.send(conversation, caption)
        return last


class _MessagingPlatformProvider(MetaBaseProvider):
    """Messenger & Instagram share the Messenger Platform webhook format."""

    webhook_object = "page"

    def _profile(self, user_id):
        try:
            fields = "name,profile_pic" if self.key == "messenger" else "name,username,profile_pic"
            return self.graph("GET", user_id, self.cred("page_access_token"), params={"fields": fields})
        except ProviderError:
            return {}

    def parse_webhook(self, request):
        body = self._body(request)
        if body.get("object") != self.webhook_object:
            return []
        results = []
        own_ids = {str(self.creds.get("page_id", "")), str(self.creds.get("ig_account_id", ""))} - {""}
        for entry in body.get("entry", []):
            # "standby": messages Meta delivers while another app (Business Suite inbox, Meta AI) owns the thread
            for event in [*entry.get("messaging", []), *entry.get("standby", [])]:
                message = event.get("message")
                if not message:
                    continue
                sender = str(event.get("sender", {}).get("id", ""))
                recipient = str(event.get("recipient", {}).get("id", ""))
                is_echo = bool(message.get("is_echo")) or sender in own_ids
                customer = recipient if is_echo else sender
                text = message.get("text", "")
                atts = [{"type": a.get("type"), "url": a.get("payload", {}).get("url")} for a in message.get("attachments", [])]
                if not text and atts:
                    text = f"[{atts[0]['type']}]"
                # Only look the profile up for new contacts (saves a Graph call per message)
                known = Contact.objects.filter(channel=self.channel, external_id=customer).exists()
                profile = {} if (is_echo or known) else self._profile(customer)
                results.append(IncomingMessage(
                    external_thread_id=customer, contact_external_id=customer,
                    contact_name=profile.get("name", ""),
                    contact_handle=f"@{profile['username']}" if profile.get("username") else "",
                    contact_avatar=profile.get("profile_pic", ""),
                    external_message_id=message.get("mid", ""), text=text, attachments=atts,
                    sent_at=_ts(event.get("timestamp"), millis=True),
                    direction="out" if is_echo else "in",
                ))
        return results

    def _send_once(self, conversation, text):
        return self.graph("POST", "me/messages", self.cred("page_access_token"), json={
            "recipient": {"id": conversation.external_thread_id},
            "messaging_type": "RESPONSE",
            "message": {"text": text},
        })

    def send(self, conversation, text):
        if conversation.meta.get("kind") == "comment":
            return self.reply_to_comment(conversation, text)
        try:
            data = self._send_once(conversation, text)
        except ProviderError as exc:
            if (exc.detail.get("error") or {}).get("error_subcode") != THREAD_CONTROLLED_ELSEWHERE:
                raise
            # Handover protocol: another app (Business Suite inbox, Meta Business AI, a chatbot)
            # owns this thread. Take control back, then retry once.
            self._take_thread_control(conversation)
            data = self._send_once(conversation, text)
        return data.get("message_id", "")

    can_send_media = True

    def send_media(self, conversation, files, text=""):
        if conversation.meta.get("kind") == "comment":
            raise ProviderError("Files can't be attached to comment replies. Use 'Send privately' with text.")
        from inbox import media
        last = ""
        for att in files:
            kind = {"image": "image", "sticker": "image", "video": "video", "audio": "audio", "voice": "audio"}.get(att.kind, "file")
            if self.key == "instagram":
                # Instagram only fetches media from a public URL; voice notes must be AAC/M4A there.
                if kind == "audio" and att.mime not in ("audio/aac", "audio/mp4", "audio/wav", "audio/x-wav"):
                    raise ProviderError("Instagram can't play this audio format. Send it as a file from WhatsApp/Messenger, "
                                        "or record on a phone (M4A).")
                payload = {"recipient": {"id": conversation.external_thread_id},
                           "message": {"attachment": {"type": kind, "payload": {"url": media.public_url(att)}}}}
                data = self.graph("POST", "me/messages", self.cred("page_access_token"), json=payload, timeout=120)
            else:
                data = self.graph("POST", "me/messages", self.cred("page_access_token"), timeout=120, data={
                    "recipient": json.dumps({"id": conversation.external_thread_id}),
                    "messaging_type": "RESPONSE",
                    "message": json.dumps({"attachment": {"type": kind, "payload": {"is_reusable": False}}}),
                }, files={"filedata": (att.name or "file", media.read_bytes(att), att.mime)})
            last = data.get("message_id", "")
        if (text or "").strip():
            last = self.send(conversation, text.strip())
        return last

    def reply_to_comment(self, conversation, text):
        """Public reply under the customer's latest comment."""
        cid = conversation.meta.get("last_comment_id")
        if not cid:
            raise ProviderError("No comment to reply to.")
        path = f"{cid}/comments" if self.key == "messenger" else f"{cid}/replies"
        data = self.graph("POST", path, self.cred("page_access_token"), json={"message": text[:8000]})
        return str(data.get("id", ""))

    def private_reply(self, conversation, text):
        """Private message (DM) to the person who commented. Meta allows one per comment, within 7 days."""
        cid = conversation.meta.get("last_comment_id")
        if not cid:
            raise ProviderError("No comment to reply to.")
        data = self.graph("POST", "me/messages", self.cred("page_access_token"),
                          json={"recipient": {"comment_id": cid}, "message": {"text": text[:2000]}})
        return str(data.get("message_id", ""))

    def _take_thread_control(self, conversation):
        try:
            self.graph("POST", "me/take_thread_control", self.cred("page_access_token"), json={
                "recipient": {"id": conversation.external_thread_id},
                "metadata": "Agent replied from OmniInbox",
            })
        except ProviderError as exc:
            if (exc.detail.get("error") or {}).get("error_subcode") in (ROUTING_DISABLED, NO_CONTROL_PERMISSION):
                raise ProviderError(ROUTING_HELP) from exc
            raise


class MessengerProvider(_MessagingPlatformProvider):
    key = "messenger"
    label = "Messenger"
    category = "social"
    color = "#0084FF"
    webhook_object = "page"
    # Webhooks for real-time delivery + polling the Conversations API as a fallback.
    # In Development mode Meta only sends webhooks for people with a role on the app,
    # but the Conversations API returns every customer's messages.
    receive_mode = "webhook + polling"
    fields = [
        Field("page_id", "Facebook Page ID"),
        Field("page_access_token", "Page access token", type="password", secret=True,
              help="Needs pages_messaging permission."),
        *MetaBaseProvider.common_fields,
    ]
    setup_steps = [
        "Create a Meta app, add the Messenger product and connect your Facebook Page.",
        "Generate a Page access token (pages_messaging).",
        "Set the webhook Callback URL + verify token, subscribe the Page to 'messages' and 'message_echoes'.",
    ]

    def verify(self):
        """Make sure we hold a *Page* token for page_id.

        People often paste a user or system-user token. If so, look the Page up in
        /me/accounts (needs only pages_show_list) and store the Page's own token instead.
        """
        page_id = str(self.cred("page_id")).strip()
        token = self.cred("page_access_token")
        try:
            accounts = self.graph("GET", "me/accounts", token, params={"fields": "id,name,access_token", "limit": "100"})
        except ProviderError:
            accounts = None  # a Page token can't list accounts -> assume it's already a Page token
        if accounts is not None:
            pages = accounts.get("data", [])
            match = next((pg for pg in pages if str(pg.get("id")) == page_id), None)
            if not match:
                listed = ", ".join(f"{pg.get('name')} ({pg.get('id')})" for pg in pages) or "none"
                raise ProviderError(
                    f"Page ID {page_id} is not one of the Pages this token can manage. "
                    f"Pages available to this token: {listed}. (Tip: the App ID is not the Page ID.)"
                )
            if match.get("access_token"):
                self.creds["page_access_token"] = match["access_token"]
                self.channel.credentials = self.creds
            return {"page": match.get("name"), "page_id": page_id}
        return {"page_id": page_id}

    @property
    def supports_polling(self):
        return True

    def poll(self):
        """Fetch new messages from the Page's Conversations API."""
        page_id = str(self.cred("page_id")).strip()
        since = self.channel.state.get("msgr_since", "")
        # First sync pulls recent history; afterwards only a small window is needed
        # (conversations are ordered by updated_time, so new activity is always at the top).
        n = "10" if since else "25"
        convs, after = [], None
        for _ in range(5):  # page through until we reach already-seen activity (max 5 pages)
            params = {
                "platform": "messenger",
                "fields": f"updated_time,participants,messages.limit({n}){{id,message,from,created_time,attachments}}",
                "limit": n,
            }
            if after:
                params["after"] = after
            data = self.graph("GET", f"{page_id}/conversations", self.cred("page_access_token"), params=params)
            page = data.get("data", [])
            convs.extend(page)
            after = (data.get("paging") or {}).get("cursors", {}).get("after")
            if not since or not page or not after or page[-1].get("updated_time", "") <= since:
                break
        results, newest = [], since
        for conv in convs:
            updated = conv.get("updated_time", "")
            if since and updated <= since:
                continue
            newest = max(newest, updated)
            people = conv.get("participants", {}).get("data", [])
            customer = next((p for p in people if str(p.get("id")) != page_id), None)
            if not customer:
                continue
            cid = str(customer["id"])
            for m in reversed(conv.get("messages", {}).get("data", [])):
                sender = str((m.get("from") or {}).get("id", ""))
                text = m.get("message") or ""
                atts = [{"type": a.get("mime_type", "file"), "mime": a.get("mime_type", ""), "name": a.get("name"),
                         "url": (a.get("image_data") or {}).get("url") or (a.get("video_data") or {}).get("url")
                         or a.get("file_url")}
                        for a in (m.get("attachments") or {}).get("data", [])]
                if not text and atts:
                    text = "[attachment]"
                results.append(IncomingMessage(
                    external_thread_id=cid, contact_external_id=cid,
                    contact_name=customer.get("name", ""),
                    external_message_id=m.get("id", ""), text=text, attachments=atts,
                    sent_at=parse_datetime(m["created_time"]) if m.get("created_time") else None,
                    direction="out" if sender == page_id else "in",
                ))
        self.channel.state["msgr_since"] = newest
        return results

    def on_connect(self):
        """Subscribe the Page to this app so Meta delivers its messages to our webhook."""
        page_id = str(self.cred("page_id")).strip()
        data = self.graph("POST", f"{page_id}/subscribed_apps", self.cred("page_access_token"),
                          params={"subscribed_fields": PAGE_FIELDS})
        if not data.get("success"):
            raise ProviderError(f"Could not subscribe the Page to the app webhook: {data}")
        return {"page_subscribed": True}


class InstagramProvider(_MessagingPlatformProvider):
    key = "instagram"
    label = "Instagram"
    category = "social"
    color = "#E1306C"
    webhook_object = "instagram"
    fields = [
        Field("ig_account_id", "Instagram business account ID"),
        Field("page_access_token", "Page access token", type="password", secret=True,
              help="Token of the Facebook Page linked to the Instagram professional account "
                   "(instagram_manage_messages)."),
        *MetaBaseProvider.common_fields,
    ]
    setup_steps = [
        "Convert the Instagram account to a Business/Creator account and link it to a Facebook Page.",
        "In your Meta app add 'Instagram' (Messenger API for Instagram) and request instagram_manage_messages.",
        "Enable 'Allow access to messages' in the Instagram app → Settings → Privacy → Messages.",
        "Set the webhook Callback URL + verify token and subscribe to the 'messages' field.",
    ]

    def verify(self):
        info = self.graph("GET", self.cred("ig_account_id"), self.cred("page_access_token"),
                          params={"fields": "id,username"})
        return {"username": info.get("username")}
