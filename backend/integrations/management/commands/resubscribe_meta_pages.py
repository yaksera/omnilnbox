"""Re-subscribe every connected Facebook Page to the app webhook (e.g. after new webhook fields were added).

    python manage.py resubscribe_meta_pages
"""
from django.core.management.base import BaseCommand

from integrations.models import ChannelAccount
from integrations.providers import get_provider
from integrations.providers.base import ProviderError


class Command(BaseCommand):
    help = "Subscribe all connected Facebook Pages to the webhook fields OmniInbox needs."

    def handle(self, *args, **opts):
        ok = failed = 0
        for ch in ChannelAccount.objects.filter(provider="messenger", is_demo=False).exclude(
                status=ChannelAccount.STATUS_DISABLED):
            try:
                get_provider(ch).on_connect()
                ok += 1
                self.stdout.write(f"  OK      {ch.name}")
            except ProviderError as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(f"  FAILED  {ch.name}: {exc}"))
        self.stdout.write(self.style.SUCCESS(f"Done: {ok} Page(s) subscribed, {failed} failed."))
