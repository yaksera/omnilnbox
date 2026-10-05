"""Give an account access to the platform admin dashboard (/admin-panel): every workspace, revenue, suspensions."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Make an OmniInbox account a platform admin (or remove it with --remove)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--remove", action="store_true")

    def handle(self, *args, **o):
        user = get_user_model().objects.filter(email__iexact=o["email"]).first()
        if not user:
            raise CommandError(f"No account with email {o['email']}. Sign up in the app first.")
        user.is_staff = not o["remove"]
        user.save(update_fields=["is_staff"])
        if o["remove"]:
            self.stdout.write(self.style.SUCCESS(f"{user.email} is no longer a platform admin."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{user.email} is now a platform admin. Log in and open Admin in the sidebar."))
            self.stdout.write("Tip: turn on two-factor login for this account (Settings → Security).")
