"""Affiliate program: applying, approval, tracking links, promo codes, recurring commissions and payouts."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.models import Payment
from billing.views import activate
from core.models import Workspace

from .models import Affiliate, Click, Commission, Payout, Referral

PASSWORD = "Kathmandu-Blue-42"
PAYOUT = {"payout_method": "esewa", "payout_details": {"account_name": "Ram Thapa", "account_number": "9800000000"}}


def signup(email, workspace, **extra):
    c = APIClient()
    r = c.post("/api/auth/register/", {"name": "Ram Thapa", "email": email, "password": PASSWORD,
                                       "workspace_name": workspace, **extra}, format="json")
    assert r.status_code == 201, r.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    return c


def pay(ws, amount="3999", currency="NPR", plan="pro", cycle="monthly", days_ago=0):
    p = Payment.objects.create(workspace=ws, plan=plan, cycle=cycle, currency=currency, amount=Decimal(amount),
                               gateway="esewa" if currency == "NPR" else "stripe")
    activate(p.id, "txn-1")
    if days_ago:
        Payment.objects.filter(id=p.id).update(paid_at=timezone.now() - timedelta(days=days_ago))
        Commission.objects.filter(payment_id=p.id).update(available_at=timezone.now() - timedelta(days=days_ago - 14))
    return p


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", EMAIL_HOST="smtp.test")
class AffiliateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = signup("founder@omni.test", "OmniInbox HQ")
        get_user_model().objects.filter(email="founder@omni.test").update(is_staff=True)
        self.aff = signup("ram@creator.test", "Ram Creates")

    def _apply_and_approve(self, code="RAM2026"):
        r = self.aff.post("/api/affiliates/me/", {**PAYOUT, "code": code, "pitch": "YouTube channel"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        a = Affiliate.objects.get(code=code)
        r = self.admin.post(f"/api/platform/affiliates/{a.id}/", {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return a

    # ---------------------------------------------------------------- applying & approval
    def test_apply_then_admin_approves(self):
        r = self.aff.get("/api/affiliates/me/")
        self.assertIsNone(r.data["affiliate"])
        self.assertEqual(r.data["program"]["rate"], "0.20")
        self.assertEqual(r.data["program"]["min_payout"]["NPR"], "2000")
        r = self.aff.post("/api/affiliates/me/", {**PAYOUT, "code": "ram 2026!"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["affiliate"]["code"], "RAM2026")
        self.assertEqual(r.data["affiliate"]["status"], "pending")
        self.assertTrue(any("New affiliate application" in m.subject for m in mail.outbox))
        # not usable until approved
        self.assertFalse(APIClient().get("/api/affiliates/code/RAM2026/").data["valid"])
        a = Affiliate.objects.get(code="RAM2026")
        self.assertEqual(self.aff.get(f"/api/platform/affiliates/{a.id}/").status_code, 403)  # not a platform admin
        self.admin.post(f"/api/platform/affiliates/{a.id}/", {"action": "approve"}, format="json")
        check = APIClient().get("/api/affiliates/code/ram2026/").data
        self.assertTrue(check["valid"])
        self.assertEqual(check["referrer"], "Ram")
        self.assertTrue(any("You're in" in m.subject for m in mail.outbox))
        # payout details are encrypted at rest but readable by the owner
        self.assertEqual(self.aff.get("/api/affiliates/me/").data["affiliate"]["payout_details"]["account_number"], "9800000000")

    def test_public_program_info(self):
        r = APIClient().get("/api/affiliates/program/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.data["rate"], r.data["hold_days"], r.data["min_payout"]["NPR"]), ("0.20", 14, "2000"))

    def test_code_rules(self):
        self.assertEqual(self.aff.post("/api/affiliates/me/", {**PAYOUT, "code": "AB"}, format="json").status_code, 400)
        self.assertEqual(self.aff.post("/api/affiliates/me/", {**PAYOUT, "code": "ADMIN"}, format="json").status_code, 400)
        r = self.aff.post("/api/affiliates/me/", {**PAYOUT, "payout_method": "bank"}, format="json")
        self.assertEqual(r.status_code, 400)  # bank needs a bank name
        r = self.aff.post("/api/affiliates/me/", PAYOUT, format="json")  # no code -> one is generated
        self.assertEqual(r.status_code, 201)
        self.assertRegex(r.data["affiliate"]["code"], r"^RAM\d{3}$")
        self.assertEqual(self.aff.post("/api/affiliates/me/", PAYOUT, format="json").status_code, 400)  # only once

    def test_code_cannot_change_after_approval(self):
        self._apply_and_approve()
        r = self.aff.patch("/api/affiliates/me/", {"code": "NEWCODE"}, format="json")
        self.assertEqual(r.status_code, 400)

    # ---------------------------------------------------------------- tracking link & promo code
    def test_link_click_and_signup_is_attributed(self):
        self._apply_and_approve()
        r = APIClient().post("/api/affiliates/click/", {"code": "RAM2026", "landing": "/pricing"}, format="json")
        self.assertTrue(r.data["valid"])
        self.assertEqual(Click.objects.count(), 1)
        signup("shop@example.com", "Sita Kurta", referral_code="RAM2026", referral_source="link")
        ref = Referral.objects.get(workspace__name="Sita Kurta")
        self.assertEqual((ref.affiliate.code, ref.source), ("RAM2026", "link"))
        stats = self.aff.get("/api/affiliates/me/").data["stats"]
        self.assertEqual((stats["clicks"], stats["signups"], stats["paying"]), (1, 1, 0))

    def test_invalid_typed_code_blocks_signup_but_stale_link_does_not(self):
        c = APIClient()
        r = c.post("/api/auth/register/", {"name": "A", "email": "a@x.test", "password": PASSWORD,
                                           "referral_code": "NOPE99"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("referral_code", r.data)
        signup("b@x.test", "B Shop", referral_code="NOPE99", referral_source="link")
        self.assertFalse(Referral.objects.exists())

    def test_promo_code_on_billing(self):
        self._apply_and_approve()
        shop = signup("shop@example.com", "Sita Kurta")
        b = shop.get("/api/billing/").data
        self.assertEqual((b["promo_code"], b["can_add_promo_code"]), (None, True))
        self.assertEqual(shop.post("/api/billing/promo-code/", {"code": "WRONG1"}, format="json").status_code, 400)
        r = shop.post("/api/billing/promo-code/", {"code": "ram2026"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        b = shop.get("/api/billing/").data
        self.assertEqual((b["promo_code"], b["can_add_promo_code"]), ("RAM2026", False))
        r = shop.post("/api/billing/promo-code/", {"code": "RAM2026"}, format="json")
        self.assertEqual(r.status_code, 400)  # only once

    def test_no_self_referral_and_no_code_after_first_payment(self):
        self._apply_and_approve()
        r = self.aff.post("/api/billing/promo-code/", {"code": "RAM2026"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("own", r.data["detail"])
        shop = signup("shop@example.com", "Sita Kurta")
        pay(Workspace.objects.get(name="Sita Kurta"))
        r = shop.post("/api/billing/promo-code/", {"code": "RAM2026"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("before the first payment", r.data["detail"])

    def test_only_owner_can_add_promo_code(self):
        self._apply_and_approve()
        shop = signup("shop@example.com", "Sita Kurta")
        shop.post("/api/team/", {"email": "agent@example.com", "role": "agent"}, format="json")
        ws = Workspace.objects.get(name="Sita Kurta")
        agent_user = get_user_model().objects.create_user("agent@example.com", "agent@example.com", PASSWORD)
        ws.memberships.create(user=agent_user, role="agent")
        agent = APIClient()
        tok = agent.post("/api/auth/login/", {"email": "agent@example.com", "password": PASSWORD}, format="json").data["access"]
        agent.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}", HTTP_X_WORKSPACE_ID=str(ws.id))
        self.assertEqual(agent.post("/api/billing/promo-code/", {"code": "RAM2026"}, format="json").status_code, 403)

    # ---------------------------------------------------------------- recurring commissions
    def test_recurring_commission_on_every_payment(self):
        self._apply_and_approve()
        signup("shop@example.com", "Sita Kurta", referral_code="RAM2026")
        ws = Workspace.objects.get(name="Sita Kurta")
        p1 = pay(ws, "3999")
        activate(p1.id, "txn-1")  # gateway retries / webhook + redirect: still one commission
        pay(ws, "3999")             # next month's renewal
        pay(ws, "38390", cycle="yearly")
        pay(ws, "29.00", currency="USD")
        amounts = sorted((c.currency, c.amount) for c in Commission.objects.all())
        self.assertEqual(amounts, [("NPR", Decimal("800")), ("NPR", Decimal("800")), ("NPR", Decimal("7678")),
                                   ("USD", Decimal("5.80"))])
        me = self.aff.get("/api/affiliates/me/").data
        self.assertEqual(me["balances"]["holding"]["NPR"], "9278")
        self.assertEqual(me["balances"]["available"]["NPR"], "0")
        self.assertEqual(me["stats"]["paying"], 1)
        self.assertEqual(me["commissions"][0]["workspace"], "Sit•••")  # affiliates don't see full customer names
        self.assertEqual(me["referrals"][0]["status"], "subscribed")

    def test_custom_rate_and_suspension(self):
        a = self._apply_and_approve()
        self.admin.post(f"/api/platform/affiliates/{a.id}/", {"action": "set_rate", "rate": "30"}, format="json")
        a.refresh_from_db()
        self.assertEqual(a.commission_rate, Decimal("0.3000"))
        signup("shop@example.com", "Sita Kurta", referral_code="RAM2026")
        ws = Workspace.objects.get(name="Sita Kurta")
        pay(ws, "1499", plan="starter")
        self.assertEqual(Commission.objects.get().amount, Decimal("450"))
        self.admin.post(f"/api/platform/affiliates/{a.id}/", {"action": "suspend", "note": "Spam ads"}, format="json")
        pay(ws, "1499", plan="starter")
        self.assertEqual(Commission.objects.count(), 1)  # suspended affiliates don't earn
        self.assertFalse(APIClient().get("/api/affiliates/code/RAM2026/").data["valid"])

    # ---------------------------------------------------------------- payouts
    def test_payout_flow(self):
        self._apply_and_approve()
        signup("shop@example.com", "Sita Kurta", referral_code="RAM2026")
        ws = Workspace.objects.get(name="Sita Kurta")
        pay(ws, "8999", plan="business", days_ago=20)  # 1800, past the 14-day hold
        r = self.aff.post("/api/affiliates/payouts/", {"currency": "NPR"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("2,000", r.data["detail"])  # below the minimum
        pay(ws, "3999", days_ago=15)  # +800 -> 2600 available
        pay(ws, "3999")               # +800 still holding
        r = self.aff.post("/api/affiliates/payouts/", {"currency": "NPR"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["amount"], "2600.00")
        self.assertEqual(self.aff.post("/api/affiliates/payouts/", {"currency": "NPR"}, format="json").status_code, 400)
        b = self.aff.get("/api/affiliates/me/").data["balances"]
        self.assertEqual((b["available"]["NPR"], b["requested"]["NPR"], b["holding"]["NPR"]), ("0", "2600", "800"))

        payout = Payout.objects.get()
        listing = self.admin.get("/api/platform/affiliate-payouts/?status=requested").data
        self.assertEqual(listing[0]["details"]["account_number"], "9800000000")
        r = self.admin.post(f"/api/platform/affiliate-payouts/{payout.id}/", {"action": "paid"}, format="json")
        self.assertEqual(r.status_code, 400)  # needs a transaction id
        r = self.admin.post(f"/api/platform/affiliate-payouts/{payout.id}/", {"action": "paid", "reference": "ESW-123"}, format="json")
        self.assertEqual(r.data["status"], "paid")
        b = self.aff.get("/api/affiliates/me/").data["balances"]
        self.assertEqual((b["paid"]["NPR"], b["requested"]["NPR"], b["lifetime"]["NPR"]), ("2600", "0", "3400"))
        self.assertTrue(any("payout" in m.subject for m in mail.outbox))
        self.assertEqual(self.admin.post(f"/api/platform/affiliate-payouts/{payout.id}/", {"action": "reject"},
                                         format="json").status_code, 400)  # already processed

    def test_rejected_payout_returns_to_balance(self):
        self._apply_and_approve()
        signup("shop@example.com", "Sita Kurta", referral_code="RAM2026")
        pay(Workspace.objects.get(name="Sita Kurta"), "38390", cycle="yearly", days_ago=30)
        r = self.aff.post("/api/affiliates/payouts/", {"currency": "NPR"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.admin.post(f"/api/platform/affiliate-payouts/{r.data['id']}/", {"action": "reject", "note": "Wrong number"}, format="json")
        b = self.aff.get("/api/affiliates/me/").data["balances"]
        self.assertEqual(b["available"]["NPR"], "7678")

    def test_admin_list_and_summary(self):
        self._apply_and_approve()
        signup("shop@example.com", "Sita Kurta", referral_code="RAM2026")
        pay(Workspace.objects.get(name="Sita Kurta"))
        r = self.admin.get("/api/platform/affiliates/")
        self.assertEqual(r.status_code, 200)
        row = r.data["results"][0]
        self.assertEqual((row["code"], row["signups"], row["paying"], row["owed"]["NPR"]), ("RAM2026", 1, 1, "800"))
        self.assertEqual(r.data["summary"]["owed"]["NPR"], "800")
        self.assertEqual(r.data["summary"]["referred_revenue"]["NPR"], "3999")
        self.assertEqual(self.aff.get("/api/platform/affiliates/").status_code, 403)
