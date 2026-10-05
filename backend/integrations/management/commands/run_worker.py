"""Background worker that polls email inboxes and polling-mode channels.

    python manage.py run_worker            # loop forever
    python manage.py run_worker --once     # single pass (use from cron)
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from integrations.sync import sync_all
from accounts.notify import unanswered_alerts
from automations.comments import poll_all as poll_comments
from commerce.services import sync_deliveries
from broadcasts.services import resume_all as resume_broadcasts
from publishing.services import publish_due


class Command(BaseCommand):
    help = "Poll email / polling-mode channels for new messages."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=settings.POLL_INTERVAL_SECONDS)

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS(f"Worker started (interval {opts['interval']}s)"))
        while True:
            close_old_connections()
            try:
                count = sync_all()
                if count:
                    self.stdout.write(f"Stored {count} new message(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Sync pass failed: {exc}")
            try:
                published = publish_due()
                if published:
                    self.stdout.write(f"Published {published} scheduled post(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Publishing pass failed: {exc}")
            try:
                answered = poll_comments()
                if answered:
                    self.stdout.write(f"Answered {answered} comment(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Comment automation pass failed: {exc}")
            try:
                alerts = unanswered_alerts()
                if alerts:
                    self.stdout.write(f"Sent {alerts} unanswered-message alert email(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Alert pass failed: {exc}")
            try:
                tracked = sync_deliveries()
                if tracked:
                    self.stdout.write(f"Updated delivery status for {tracked} order(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Delivery tracking pass failed: {exc}")
            try:
                from automations.sales import send_followups, send_visit_reminders
                nudged = send_followups()
                reminded_visits = send_visit_reminders()
                if nudged or reminded_visits:
                    self.stdout.write(f"AI sent {nudged} follow-up(s) and {reminded_visits} visit reminder(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Follow-up pass failed: {exc}")
            try:
                resumed = resume_broadcasts()
                if resumed:
                    self.stdout.write(f"Sent {resumed} broadcast message(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Broadcast pass failed: {exc}")
            try:
                from inbox.media import retry_pending
                retry_pending()  # finish file downloads interrupted by a restart; clean up unsent uploads
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"File download pass failed: {exc}")
            try:
                from billing.reminders import send_renewal_reminders
                reminded = send_renewal_reminders()
                if reminded:
                    self.stdout.write(f"Sent {reminded} renewal reminder email(s)")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"Renewal reminder pass failed: {exc}")
            if opts["once"]:
                break
            time.sleep(opts["interval"])
