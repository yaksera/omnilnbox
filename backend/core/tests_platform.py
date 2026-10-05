"""Platform admin dashboard, suspending workspaces, renewal reminder emails."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.models import Payment
from billing.reminders import send_renewal_reminders
from core.models import Workspace
from integrations.models import ChannelAccount

PASSWORD = "Kathmandu-Blue-42"


def signup(email, workspace):
    c = APIClient()
    r = c.post("/api/auth/register/", {"name": "Owner", "email": email, "password": PASSWORD, "workspace_name": workspace},
               format="json")
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    return c


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", EMAIL_HOST="smtp.test")
class PlatformAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = signup("founder@omni.test", "OmniInbox HQ")
        self.shop = signup("shop@example.com", "Sita Kurta")
        self.ws = Workspace.objects.get(name="Sita Kurta")

    def test_only_platform_admins_can_open_it(self):
        self.assertEqual(self.admin.get("/api/platform/overview/").status_code, 403)
        call_command("make_platform_admin", "founder@omni.test", stdout=open("/dev/null", "w"))
        self.assertEqual(self.admin.get("/api/auth/me/").data["user"]["is_platform_admin"], True)
        self.assertEqual(self.admin.get("/api/platform/overview/").status_code, 200)
        self.assertEqual(self.shop.get("/api/platform/workspaces/").status_code, 403)

    def test_overview_counts_revenue_and_mrr(self):
        get_user_model().objects.filter(email="founder@omni.test").update(is_staff=True)
        now = timezone.now()
        Workspace.objects.filter(pk=self.ws.pk).update(plan="pro", plan_expires_at=now + timedelta(days=20), trial_ends_at=None,
                                                       currency="NPR", billing_cycle="monthly")
        Payment.objects.create(workspace=self.ws, plan="pro", cycle="monthly", currency="NPR", amount=Decimal("3999"),
                               gateway="khalti", status="paid", paid_at=now)
        data = self.admin.get("/api/platform/overview/").data
        self.assertEqual(data["workspaces"]["paying"], 1)
        self.assertEqual(data["workspaces"]["trial"], 1)  # the admin's own new workspace is on the trial
        self.assertEqual(data["mrr"]["NPR"], "3999.00")
        self.assertEqual(data["revenue"]["this_month"]["NPR"], "3999.00")
        rows = self.admin.get("/api/platform/workspaces/", {"filter": "paying"}).data["results"]
        self.assertEqual([r["name"] for r in rows], ["Sita Kurta"])
        self.assertEqual(rows[0]["owner"]["email"], "shop@example.com")
        self.assertEqual(rows[0]["total_paid"]["NPR"], "3999.00")
        found = self.admin.get("/api/platform/workspaces/", {"q": "shop@example"}).data
        self.assertEqual(found["count"], 1)

    @override_settings(AI_COST_PER_MILLION_TOKENS_USD="4")
    def test_insights_ai_usage_users_affiliates_activity(self):
        from automations.models import AIUsage
        from affiliates.models import Affiliate, Referral
        from inbox.models import Contact, Conversation, Message
        self.assertEqual(self.shop.get("/api/platform/insights/").status_code, 403)
        get_user_model().objects.filter(email="founder@omni.test").update(is_staff=True)
        month = timezone.localdate().replace(day=1)
        AIUsage.objects.create(workspace=self.ws, month=month, credits=2900, tokens=1_500_000)  # Pro allows 3000
        aff = Affiliate.objects.create(user=get_user_model().objects.get(email="founder@omni.test"), code="FOUNDER1",
                                       status="approved")
        Referral.objects.create(workspace=self.ws, affiliate=aff)
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="TG", status="active", credentials={})
        contact = Contact.objects.create(workspace=self.ws, channel=ch, external_id="1", name="Ram")
        conv = Conversation.objects.create(workspace=self.ws, channel=ch, contact=contact)
        now = timezone.now()
        Message.objects.create(conversation=conv, direction="in", text="price?", sent_at=now)
        Message.objects.create(conversation=conv, direction="out", text="Rs 500", bot="ai", sent_at=now, status="sent")
        d = self.admin.get("/api/platform/insights/").data
        self.assertEqual(d["users"]["total"], 2)
        self.assertEqual(d["users"]["signups"]["d30"], 2)
        self.assertEqual((d["ai"]["credits"], d["ai"]["tokens"], d["ai"]["cost_usd"]), (2900, 1_500_000, "6.00"))
        self.assertEqual(d["ai"]["near_limit"], 1)
        self.assertEqual(d["ai"]["top"][0]["name"], "Sita Kurta")
        self.assertEqual(d["ai"]["bot_replies"]["d30"], 1)
        self.assertEqual((d["affiliates"]["approved"], d["affiliates"]["referrals"]), (1, 1))
        self.assertEqual(d["activity"]["messages_30d"], {"in": 1, "out": 1})
        self.assertEqual(d["activity"]["channels"], [{"provider": "telegram", "count": 1}])
        self.assertEqual(d["funnel"]["created_90d"], 2)

    def test_suspend_blocks_the_workspace_everywhere_and_unsuspend_restores(self):
        get_user_model().objects.filter(email="founder@omni.test").update(is_staff=True)
        site = ChannelAccount.objects.create(workspace=self.ws, provider="website", name="Site", status="active", credentials={})
        url = f"/api/platform/workspaces/{self.ws.id}/"
        self.assertEqual(self.admin.post(url, {"action": "suspend"}, format="json").status_code, 400)  # needs a reason
        r = self.admin.post(url, {"action": "suspend", "reason": "Spam complaints"}, format="json")
        self.assertEqual(r.data["status"], "suspended")
        blocked = self.shop.get("/api/conversations/")
        self.assertEqual(blocked.status_code, 403)
        self.assertIn("Spam complaints", str(blocked.data["detail"]))
        me = self.shop.get("/api/auth/me/")  # the app can still load to show the "suspended" screen
        self.assertEqual(me.data["workspace"]["suspended"]["reason"], "Spam complaints")
        self.assertEqual(APIClient().get(f"/api/widget/{site.id}/").status_code, 404)  # website chat off
        self.assertEqual(self.admin.post(url, {"action": "unsuspend"}, format="json").data["status"], "trial")
        self.assertEqual(self.shop.get("/api/conversations/").status_code, 200)
        from accounts.models import AuditLog
        self.assertEqual(AuditLog.objects.filter(workspace=self.ws, action__startswith="platform.").count(), 2)

    def test_extend_plan_by_hand(self):
        get_user_model().objects.filter(email="founder@omni.test").update(is_staff=True)
        r = self.admin.post(f"/api/platform/workspaces/{self.ws.id}/", {"action": "extend", "days": 30, "plan": "business"},
                            format="json")
        self.ws.refresh_from_db()
        self.assertEqual((r.data["status"], self.ws.plan, self.ws.trial_ends_at), ("paying", "business", None))

    def test_renewal_reminders_are_sent_once_per_stage(self):
        now = timezone.now()
        Workspace.objects.filter(pk=self.ws.pk).update(plan="pro", trial_ends_at=None, plan_expires_at=now + timedelta(days=6))
        Workspace.objects.exclude(pk=self.ws.pk).update(plan_expires_at=now + timedelta(days=30))
        mail.outbox.clear()
        self.assertEqual(send_renewal_reminders(now), 1)
        self.assertIn("ends in 7 days", mail.outbox[-1].subject)
        self.assertEqual(mail.outbox[-1].to, ["shop@example.com"])
        self.assertEqual(send_renewal_reminders(now), 0)  # not twice
        self.assertEqual(send_renewal_reminders(now + timedelta(days=4)), 1)  # 2 days left -> "3 days" stage
        self.assertIn("ends in 3 days", mail.outbox[-1].subject)
        self.assertEqual(send_renewal_reminders(now + timedelta(days=5, hours=12)), 1)
        self.assertIn("ends in 1 day", mail.outbox[-1].subject)
        self.assertEqual(send_renewal_reminders(now + timedelta(days=6, hours=2)), 1)
        self.assertIn("has ended", mail.outbox[-1].subject)
        self.assertEqual(send_renewal_reminders(now + timedelta(days=6, hours=5)), 0)
        self.assertIn("/billing", mail.outbox[-1].body)

    def test_trial_reminder_wording_and_late_start(self):
        now = timezone.now()
        ws = Workspace.objects.get(pk=self.ws.pk)
        Workspace.objects.exclude(pk=ws.pk).update(plan_expires_at=now + timedelta(days=30))
        Workspace.objects.filter(pk=ws.pk).update(plan_expires_at=now + timedelta(hours=20), trial_ends_at=now + timedelta(hours=20))
        mail.outbox.clear()
        self.assertEqual(send_renewal_reminders(now), 1)  # only the most urgent one, no "7 days left" too
        self.assertIn("free Pro trial ends in 1 day", mail.outbox[-1].subject)
