"""Send due renewal reminder emails now (the worker also does this automatically)."""
from django.core.management.base import BaseCommand

from billing.reminders import send_renewal_reminders


class Command(BaseCommand):
    help = "Email workspace owners whose plan or trial ends within 7 days (or just ended)."

    def handle(self, *args, **o):
        n = send_renewal_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {n} renewal reminder(s)."))
