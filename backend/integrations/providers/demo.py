"""Demo mode: simulated channels with seeded conversations and auto-replies.

Lets you run and show the product without any API keys. Demo channels never call
external APIs.
"""
import random
from datetime import timedelta

from django.utils import timezone

from .base import BaseProvider, IncomingMessage

SEED = {
    "whatsapp": [
        ("Aarav Sharma", "+977 9801234567", "Hi! Is the blue hoodie still available in size M?"),
        ("Priya Karki", "+977 9812345678", "Can I change my delivery address for order #1042?"),
    ],
    "instagram": [
        ("Maya Thapa", "@maya.creates", "Loved your latest reel 😍 do you ship to Pokhara?"),
        ("Rohan Joshi", "@rohanj", "What's the price for the leather wallet?"),
    ],
    "messenger": [
        ("Sita Gurung", "Sita Gurung", "Hello, what are your opening hours on Saturday?"),
    ],
    "tiktok": [
        ("dancewithkiran", "@dancewithkiran", "Saw your video! Where can I buy that jacket?"),
    ],
    "telegram": [
        ("Bikash Rai", "@bikashrai", "Payment done via eSewa. Please confirm 🙏"),
    ],
    "discord": [
        ("pixelwolf", "@pixelwolf", "Hey, the download link in #announcements is broken."),
    ],
    "gmail": [
        ("Emily Carter", "emily.carter@example.com", "Partnership proposal for Q4\n\nHi team, we'd love to discuss a collaboration for our upcoming campaign. Are you free next week?"),
    ],
    "outlook": [
        ("James Lee", "james.lee@contoso.example", "Invoice INV-2291 overdue\n\nHello, just a reminder that invoice INV-2291 is now 5 days overdue."),
    ],
    "zoho": [
        ("Anita Shrestha", "anita@shresthatraders.example", "Bulk order quote\n\nNamaste, could you send a quote for 200 units of the canvas tote bags?"),
    ],
}

AUTO_REPLIES = [
    "Thanks! That helps a lot 🙌",
    "Perfect, thank you for the quick reply.",
    "Great, I'll wait for the update.",
    "Okay 👍 one more question — do you offer gift wrapping?",
    "Awesome, appreciate it!",
]


def seed_demo_workspace(workspace, user=None):
    """Create one demo channel per provider with sample conversations."""
    from inbox.services import ingest_message
    from integrations.models import ChannelAccount
    from integrations.providers import PROVIDERS

    created = []
    now = timezone.now()
    for i, (provider_key, threads) in enumerate(SEED.items()):
        label = PROVIDERS[provider_key].label
        channel, is_new = ChannelAccount.objects.get_or_create(
            workspace=workspace, provider=provider_key, is_demo=True,
            defaults={"name": f"{label} (demo)", "status": ChannelAccount.STATUS_ACTIVE, "created_by": user},
        )
        if not is_new:
            continue
        created.append(channel)
        for j, (name, handle, text) in enumerate(threads):
            subject = ""
            body = text
            if PROVIDERS[provider_key].category == "email":
                subject, _, body = text.partition("\n\n")
            thread_id = f"demo-{provider_key}-{j}"
            t0 = now - timedelta(minutes=(i * 17 + j * 9 + 5))
            ingest_message(channel, IncomingMessage(
                external_thread_id=thread_id, contact_external_id=f"{provider_key}-{j}",
                contact_name=name, contact_handle=handle, text=body, subject=subject,
                external_message_id=f"{thread_id}-1", sent_at=t0,
            ))
    return created


class DemoProvider(BaseProvider):
    """Wraps any demo channel: sending succeeds locally and the 'customer' answers back."""

    def __init__(self, channel, real_cls):
        super().__init__(channel)
        self.real_cls = real_cls
        self.key = real_cls.key
        self.label = real_cls.label
        self.receive_mode = "demo"

    def verify(self):
        return {"demo": True}

    def on_connect(self):
        return {}

    def send(self, conversation, text):
        return f"demo-out-{timezone.now().timestamp()}"

    can_send_media = True

    def send_media(self, conversation, files, text=""):
        return f"demo-out-{timezone.now().timestamp()}"

    def after_send(self, conversation, text):
        from inbox.services import ingest_message
        ingest_message(self.channel, IncomingMessage(
            external_thread_id=conversation.external_thread_id,
            contact_external_id=conversation.contact.external_id,
            text=random.choice(AUTO_REPLIES),
            external_message_id=f"demo-in-{timezone.now().timestamp()}",
            sent_at=timezone.now() + timedelta(seconds=2),
        ))
