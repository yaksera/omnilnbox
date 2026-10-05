"""Outlook / Microsoft 365 via Microsoft Graph with OAuth 2.0 (authorization code flow).

Microsoft disabled basic-auth IMAP for Outlook.com, so we use Graph:
  * receive: poll /me/mailFolders/inbox/messages (grouped by conversationId)
  * send:    POST /me/messages/{id}/reply

Setup: register an app in Azure (Entra ID) → App registrations with
  redirect URI  = <PUBLIC_BASE_URL>/api/oauth/microsoft/callback/
  API permissions (delegated) = offline_access, User.Read, Mail.ReadWrite, Mail.Send
"""
import time

from django.conf import settings
from django.utils.dateparse import parse_datetime

from .base import BaseProvider, Field, IncomingMessage, ProviderError
from .email_imap import _html_to_text, _strip_quoted

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = "offline_access User.Read Mail.ReadWrite Mail.Send"


def redirect_uri():
    return f"{settings.PUBLIC_BASE_URL}/api/oauth/microsoft/callback/"


class OutlookProvider(BaseProvider):
    key = "outlook"
    label = "Outlook"
    category = "email"
    color = "#0078D4"
    receive_mode = "oauth-polling"
    uses_oauth = True
    fields = [
        Field("client_id", "Application (client) ID"),
        Field("client_secret", "Client secret", type="password", secret=True),
        Field("tenant", "Tenant", default="common", required=False,
              help="'common' for personal + work accounts, or your tenant ID."),
    ]
    setup_steps = [
        "Azure Portal → Microsoft Entra ID → App registrations → New registration (any account type).",
        "Add a Web redirect URI: <PUBLIC_BASE_URL>/api/oauth/microsoft/callback/",
        "Add delegated permissions: offline_access, User.Read, Mail.ReadWrite, Mail.Send.",
        "Create a client secret, save this channel, then click 'Authorize with Microsoft'.",
    ]

    @property
    def tenant(self):
        return self.creds.get("tenant") or "common"

    @property
    def token_url(self):
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token"

    def authorize_url(self, state):
        from urllib.parse import urlencode
        q = urlencode({
            "client_id": self.cred("client_id"), "response_type": "code", "redirect_uri": redirect_uri(),
            "response_mode": "query", "scope": SCOPES, "state": state, "prompt": "select_account",
        })
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/authorize?{q}"

    def _store_tokens(self, data):
        self.creds["access_token"] = data["access_token"]
        if data.get("refresh_token"):
            self.creds["refresh_token"] = data["refresh_token"]
        self.creds["expires_at"] = int(time.time()) + int(data.get("expires_in", 3600)) - 60
        self.channel.credentials = self.creds
        self.channel.save(update_fields=["credentials"])

    def exchange_code(self, code):
        data = self.http("POST", self.token_url, data={
            "client_id": self.cred("client_id"), "client_secret": self.cred("client_secret"),
            "code": code, "redirect_uri": redirect_uri(), "grant_type": "authorization_code", "scope": SCOPES,
        })
        self._store_tokens(data)

    def _token(self):
        if not self.creds.get("refresh_token"):
            raise ProviderError("Not authorized yet — click 'Authorize with Microsoft'.")
        if self.creds.get("access_token") and int(self.creds.get("expires_at", 0)) > time.time():
            return self.creds["access_token"]
        data = self.http("POST", self.token_url, data={
            "client_id": self.cred("client_id"), "client_secret": self.cred("client_secret"),
            "refresh_token": self.creds["refresh_token"], "grant_type": "refresh_token", "scope": SCOPES,
        })
        self._store_tokens(data)
        return self.creds["access_token"]

    def _graph(self, method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token()}"
        return self.http(method, f"{GRAPH}{path}", headers=headers, **kwargs)

    def verify(self):
        me = self._graph("GET", "/me", params={"$select": "mail,userPrincipalName,displayName"})
        email_addr = me.get("mail") or me.get("userPrincipalName")
        self.channel.state["email"] = email_addr
        return {"email": email_addr, "name": me.get("displayName")}

    def poll(self):
        own = (self.channel.state.get("email") or "").lower()
        since = self.channel.state.get("last_received")
        params = {
            "$top": "50", "$orderby": "receivedDateTime asc",
            "$select": "id,internetMessageId,conversationId,subject,from,receivedDateTime,body,bodyPreview,hasAttachments",
        }
        if since:
            params["$filter"] = f"receivedDateTime gt {since}"
        else:
            from datetime import datetime, timedelta, timezone
            start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            params["$filter"] = f"receivedDateTime ge {start}"
        data = self._graph("GET", "/me/mailFolders/inbox/messages", params=params,
                           headers={"Prefer": 'outlook.body-content-type="html"'})
        results = []
        for m in data.get("value", []):
            self.channel.state["last_received"] = m["receivedDateTime"]
            sender = (m.get("from") or {}).get("emailAddress", {})
            addr = (sender.get("address") or "").lower()
            if own and addr == own:
                continue
            html = (m.get("body") or {}).get("content", "")
            text = _strip_quoted(_html_to_text(html)) if html else m.get("bodyPreview", "")
            files = []
            if m.get("hasAttachments"):
                try:
                    listed = self._graph("GET", f"/me/messages/{m['id']}/attachments",
                                         params={"$select": "id,name,contentType,size,isInline"})
                    files = [{"type": a.get("contentType", "file"), "mime": a.get("contentType", ""), "name": a.get("name", ""),
                              "graph_message_id": m["id"], "attachment_id": a["id"]}
                             for a in listed.get("value", []) if a.get("@odata.type", "").endswith("fileAttachment")]
                except ProviderError:
                    files = [{"type": "file"}]
            results.append(IncomingMessage(
                external_thread_id=m["conversationId"], contact_external_id=addr or m["id"],
                contact_name=sender.get("name", ""), contact_handle=addr,
                external_message_id=m.get("internetMessageId") or m["id"],
                text=text, html=html[:200000], subject=m.get("subject", ""),
                attachments=files,
                sent_at=parse_datetime(m["receivedDateTime"]),
                thread_meta={"graph_last_message_id": m["id"], "reply_to": addr},
            ))
        return results

    def send(self, conversation, text):
        msg_id = (conversation.meta or {}).get("graph_last_message_id")
        if not msg_id:
            raise ProviderError("No message to reply to in this thread.")
        self._graph("POST", f"/me/messages/{msg_id}/reply", json={"comment": text})
        return ""

    can_send_media = True

    def fetch_attachment(self, source):
        import base64
        a = self._graph("GET", f"/me/messages/{source.get('graph_message_id')}/attachments/{source.get('attachment_id')}")
        return base64.b64decode(a.get("contentBytes") or ""), a.get("contentType", ""), a.get("name", "")

    def send_media(self, conversation, files, text=""):
        """Reply with attachments: create a reply draft, attach the files (max 3 MB each), send it."""
        import base64
        from inbox.media import read_bytes
        msg_id = (conversation.meta or {}).get("graph_last_message_id")
        if not msg_id:
            raise ProviderError("No message to reply to in this thread.")
        if any(a.size > 3 * 1024 * 1024 for a in files):
            raise ProviderError("Outlook attachments sent from OmniInbox can be at most 3 MB each.")
        draft = self._graph("POST", f"/me/messages/{msg_id}/createReply", json={"comment": text or ""})
        for att in files:
            self._graph("POST", f"/me/messages/{draft['id']}/attachments", json={
                "@odata.type": "#microsoft.graph.fileAttachment", "name": att.name or "file",
                "contentType": att.mime, "contentBytes": base64.b64encode(read_bytes(att)).decode()})
        self._graph("POST", f"/me/messages/{draft['id']}/send")
        return ""
