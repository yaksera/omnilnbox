"""Provider interface every channel connector implements."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests


class ProviderError(Exception):
    """Raised for configuration or remote API errors. The message is shown to the user."""

    def __init__(self, message, status=None, detail=None):
        super().__init__(message)
        self.status = status
        self.detail = detail if isinstance(detail, dict) else {}


@dataclass
class IncomingMessage:
    external_thread_id: str
    contact_external_id: str
    text: str = ""
    external_message_id: str = ""
    contact_name: str = ""
    contact_handle: str = ""
    contact_avatar: str = ""
    sender_name: str = ""
    subject: str = ""
    html: str = ""
    sent_at: Optional[datetime] = None
    attachments: list = field(default_factory=list)
    direction: str = "in"  # "out" for messages sent from the native app (echoes)
    thread_meta: dict = field(default_factory=dict)  # stored on the Conversation (reply info)


@dataclass
class Field:
    name: str
    label: str
    type: str = "text"  # text | password | number | select
    required: bool = True
    secret: bool = False
    help: str = ""
    default: str = ""
    options: list = field(default_factory=list)

    def as_dict(self):
        return {
            "name": self.name, "label": self.label, "type": self.type, "required": self.required,
            "secret": self.secret, "help": self.help, "default": self.default, "options": self.options,
        }


class BaseProvider:
    key = ""
    label = ""
    category = "chat"  # chat | social | email
    color = "#64748b"
    fields: list = []
    receive_mode = "webhook"  # webhook | polling | gateway | oauth-polling
    default_receive_mode = "webhook"  # used by describe() when receive_mode is dynamic
    setup_steps: list = []
    uses_oauth = False
    beta = False
    can_send_media = False  # photos, videos, voice notes, files from the inbox composer

    def __init__(self, channel):
        self.channel = channel
        self.creds = channel.credentials or {}

    # ----- metadata -----------------------------------------------------
    @classmethod
    def describe(cls):
        return {
            "key": cls.key, "label": cls.label, "category": cls.category, "color": cls.color,
            "fields": [f.as_dict() for f in cls.fields],
            "receive_mode": cls.receive_mode if isinstance(cls.receive_mode, str) else cls.default_receive_mode,
            "setup_steps": cls.setup_steps, "uses_oauth": cls.uses_oauth, "beta": cls.beta,
            "can_send_media": cls.can_send_media,
        }

    def cred(self, name, default=None):
        value = self.creds.get(name, default)
        if value in (None, "") and default is None:
            raise ProviderError(f"Missing credential: {name}")
        return value

    # ----- lifecycle ----------------------------------------------------
    def verify(self) -> dict:
        """Check the credentials against the remote API. Return info to display."""
        return {}

    def on_connect(self) -> dict:
        """Called after the channel is created/updated (e.g. register a webhook)."""
        return {}

    # ----- receiving ----------------------------------------------------
    def webhook_challenge(self, request):
        """Return an HttpResponse for GET verification handshakes, or None."""
        return None

    def validate_webhook(self, request) -> bool:
        """Fail closed: providers that receive webhooks must verify the platform's signature."""
        return False

    def parse_webhook(self, request) -> list:
        return []

    def poll(self) -> list:
        return []

    @property
    def supports_polling(self):
        return self.receive_mode in ("polling", "oauth-polling")

    # ----- sending ------------------------------------------------------
    def send(self, conversation, text) -> str:
        raise ProviderError(f"Sending is not implemented for {self.label}")

    def send_media(self, conversation, files, text="") -> str:
        """Send inbox.Attachment objects (and optional text). Returns the platform id of the last message."""
        raise ProviderError(f"{self.label} doesn't support sending files from OmniInbox yet. Send the text only.")

    def fetch_attachment(self, source) -> tuple:
        """Download a customer's file. Returns (bytes, mime, filename)."""
        from inbox.media import download_url
        if source.get("url"):
            return download_url(source["url"])
        raise ProviderError("This platform didn't include a download link for the file.")

    # ----- helpers ------------------------------------------------------
    @staticmethod
    def http(method, url, **kwargs):
        kwargs.setdefault("timeout", 20)
        resp = requests.request(method, url, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text[:500]
            raise ProviderError(f"{resp.status_code} from {url.split('?')[0]}: {detail}",
                                status=resp.status_code, detail=detail)
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}
