"""Registry of all channel providers."""
from .base import BaseProvider, IncomingMessage, ProviderError  # noqa: F401
from .demo import DemoProvider
from .discord import DiscordProvider
from .email_imap import GmailProvider, ImapEmailProvider, ZohoProvider
from .meta import InstagramProvider, MessengerProvider, WhatsAppProvider
from .outlook import OutlookProvider
from .telegram import TelegramProvider
from .tiktok import TikTokProvider
from .viber import ViberProvider
from .website import WebsiteProvider

PROVIDERS = {
    cls.key: cls
    for cls in [
        WhatsAppProvider, InstagramProvider, MessengerProvider, TikTokProvider,
        TelegramProvider, ViberProvider, DiscordProvider, WebsiteProvider,
        GmailProvider, OutlookProvider, ZohoProvider, ImapEmailProvider,
    ]
}


def get_provider_class(key):
    return PROVIDERS.get(key)


def get_provider(channel) -> BaseProvider:
    cls = PROVIDERS.get(channel.provider)
    if cls is None:
        raise ProviderError(f"Unknown provider {channel.provider}")
    if channel.is_demo:
        return DemoProvider(channel, cls)
    return cls(channel)
