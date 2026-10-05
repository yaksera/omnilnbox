from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def give_trial(apps, schema_editor):
    """Workspaces created before billing existed get the standard 14-day Pro trial."""
    Workspace = apps.get_model("core", "Workspace")
    end = timezone.now() + timedelta(days=14)
    for ws in Workspace.objects.filter(plan_expires_at__isnull=True, trial_ends_at__isnull=True):
        if ws.plan in ("free", "pro"):
            ws.plan, ws.trial_ends_at, ws.plan_expires_at = "pro", end, end
            ws.save(update_fields=["plan", "trial_ends_at", "plan_expires_at"])


class Migration(migrations.Migration):
    dependencies = [("core", "0002_workspace_agents_see_all_workspace_billing_cycle_and_more")]
    operations = [migrations.RunPython(give_trial, migrations.RunPython.noop)]
