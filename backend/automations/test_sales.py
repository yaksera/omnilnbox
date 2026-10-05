"""AI sales staff: voice notes, payment screenshots, orders and visits taken in chat, follow-ups, auto courier booking."""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone

from commerce.models import Booking, Order, PaymentCheck, Product, ShopSettings
from inbox.models import Attachment, Conversation, Message
from inbox.services import ingest_message
from integrations.models import ChannelAccount
from integrations.providers import IncomingMessage

from . import engine, sales
from .models import AssistantSettings, FollowUp
from .tests import Base, llm_returns

NO_ACTION = {"handoff": False, "reason": "", "category": "order", "sentiment": "positive", "sources": [],
             "stage": "interested", "interest": "kurta", "action": "none"}


def answer(**kw):
    return {**NO_ACTION, "reply": "Ok!", **kw}


class SalesBase(Base):
    def setUp(self):
        super().setUp()
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.bot_mode = cfg.BOT_ALWAYS
        cfg.sales_orders = cfg.sales_bookings = True
        cfg.hours = {d: {"on": True, "start": "00:00", "end": "23:59"} for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        cfg.save()
        self.cfg = cfg
        self.kurta = Product.objects.create(workspace=self.ws, name="Cotton kurta", price=Decimal("1800"), variants=["M", "L"], stock=5)

    def conv(self, thread="t1"):
        return Conversation.objects.get(external_thread_id=thread)

    def notes(self, thread="t1"):
        return list(self.conv(thread).messages.filter(is_note=True).values_list("text", flat=True))


class OrderTakingTests(SalesBase):
    ORDER = {"items": [{"product_id": None, "option": "M", "quantity": 2}], "name": "Sita Sharma", "phone": "9841234567",
             "address": "Baneshwor-10", "city": "Kathmandu", "district": "Kathmandu", "payment": "cod"}

    def order(self, **kw):
        o = {**self.ORDER, **kw}
        o["items"] = [{**o["items"][0], "product_id": self.kurta.id}] if o["items"][0]["product_id"] is None else o["items"]
        return o

    def test_catalogue_in_prompt_and_summary_uses_database_prices(self):
        patch, calls = llm_returns(answer(reply="Here is your order 🙏", action="propose_order", stage="ready",
                                          order={**self.order(), "items": [{"product_id": self.kurta.id, "option": "m",
                                                                             "quantity": 2, "unit_price": 1}]}))
        with patch:
            self.customer_says("2 ta M size kurta, Sita Sharma 9841234567 Baneshwor Kathmandu, COD")
        system = calls[0][0]["content"]
        self.assertIn(f"P{self.kurta.id} | Cotton kurta | Rs 1,800", system)
        text = self.outgoing()[-1][1]
        self.assertIn("2 × Cotton kurta (M) = Rs 3,600", text)  # price from the database, not the model
        self.assertIn("Delivery: Rs 100", text)  # inside the valley
        self.assertIn("Total: Rs 3,700", text)
        self.assertIn("Reply YES", text)
        self.assertEqual(Order.objects.count(), 0)  # nothing created before the customer confirms
        self.assertIn("order_draft", self.conv().meta)

    def test_customer_confirms_and_order_is_created(self):
        with llm_returns(answer(reply="Here you go", action="propose_order", stage="ready", order=self.order()))[0]:
            self.customer_says("order please")
        patch, calls = llm_returns(answer(reply="Thank you!", action="confirm_order", stage="done"))
        with patch:
            self.customer_says("yes")
        self.assertIn("Order waiting for the customer's confirmation: 2 × Cotton kurta (M)", calls[0][0]["content"])
        order = Order.objects.get()
        self.assertEqual((order.source, order.status, order.payment_method, order.total), ("ai", "confirmed", "cod", Decimal("3700")))
        self.assertEqual(order.conversation, self.conv())
        self.assertEqual(Product.objects.get().stock, 3)
        self.assertIn(order.number, self.outgoing()[-1][1])
        self.assertTrue(any("AI took order" in n for n in self.notes()))
        self.assertNotIn("order_draft", self.conv().meta)

    def test_incomplete_order_asks_again_instead_of_proposing(self):
        patch, calls = llm_returns(
            answer(reply="Summary:", action="propose_order", order=self.order(phone="123")),
            answer(reply="Tapai ko mobile number pathaunus na?", action="none", stage="collecting_details"))
        with patch:
            self.customer_says("order")
        self.assertIn("valid 10-digit mobile number is missing", calls[1][-1]["content"])
        self.assertEqual(self.outgoing()[-1][1], "Tapai ko mobile number pathaunus na?")
        self.assertNotIn("order_draft", self.conv().meta)

    def test_unknown_product_and_missing_option_are_rejected(self):
        draft, errors = sales.build_draft(self.ws, self.order(items=[{"product_id": 999, "quantity": 1}]))
        self.assertIsNone(draft)
        self.assertIn("isn't in the catalogue", errors[0])
        _, errors = sales.build_draft(self.ws, self.order(items=[{"product_id": self.kurta.id, "quantity": 1}]))
        self.assertIn("which option", errors[0])
        _, errors = sales.build_draft(self.ws, self.order(items=[{"product_id": self.kurta.id, "option": "L", "quantity": 9}]))
        self.assertIn("only 5", errors[0])

    def test_confirm_without_a_draft_does_not_create_an_order(self):
        with llm_returns(answer(action="confirm_order"), answer(reply="Which product would you like?"))[0]:
            self.customer_says("yes")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.outgoing()[-1][1], "Which product would you like?")


class VisitTests(SalesBase):
    def when(self, hours=26):
        t = timezone.localtime(timezone.now() + timedelta(hours=hours), sales._tz(self.cfg))
        return t.replace(minute=0).strftime("%Y-%m-%d %H:%M")

    def test_ai_books_a_visit(self):
        visit = {"name": "Ram Thapa", "phone": "9801234567", "starts_at": self.when(), "purpose": "IELTS + Australia"}
        with llm_returns(answer(reply="Booking it now", action="book_visit", visit=visit))[0]:
            self.customer_says("Bholi 2 baje counselling ko lagi aauna milcha?")
        b = Booking.objects.get()
        self.assertEqual((b.name, b.phone, b.purpose, b.source), ("Ram Thapa", "9801234567", "IELTS + Australia", "ai"))
        self.assertIn("Visit booked for", self.outgoing()[-1][1])
        self.assertTrue(any("AI booked" in n for n in self.notes()))

    def test_full_slot_offers_other_times(self):
        start = sales._parse_when(self.when(), sales._tz(self.cfg))
        for i in range(self.cfg.booking_capacity):
            Booking.objects.create(workspace=self.ws, name=f"x{i}", starts_at=start)
        visit = {"name": "Ram Thapa", "phone": "9801234567", "starts_at": self.when()}
        patch, calls = llm_returns(answer(action="book_visit", visit=visit), answer(reply="That time is full, how about 3pm?"))
        with patch:
            self.customer_says("book me")
        self.assertIn("fully booked", calls[1][-1]["content"])
        self.assertIn("Free times:", calls[1][-1]["content"])
        self.assertEqual(Booking.objects.count(), 2)

    def test_closed_hours_rejected(self):
        self.cfg.hours = {d: {"on": d != "sat", "start": "10:00", "end": "17:00"} for d in sales.DAYS}
        self.cfg.save()
        _, _, errors = sales.check_visit(self.cfg, {"name": "Ram", "phone": "9801234567", "starts_at": "2030-01-05 20:00"})
        self.assertTrue(errors)


class FollowUpTests(SalesBase):
    def setUp(self):
        super().setUp()
        self.cfg.followup_enabled = True
        self.cfg.followup_hours = 3
        self.cfg.save()

    def test_interested_customer_gets_one_follow_up(self):
        with llm_returns(answer(reply="Kurta Rs 1,800 ho", stage="interested", interest="cotton kurta"))[0]:
            self.customer_says("kurta kati ho?")
        fu = FollowUp.objects.get()
        self.assertEqual(fu.reason, "cotton kurta")
        FollowUp.objects.update(due_at=timezone.now() - timedelta(minutes=1))
        with llm_returns("Namaste! Kurta ko barema kei jijnasa cha?")[0]:
            self.assertEqual(sales.send_followups(), 1)
        self.assertEqual(self.outgoing()[-1], ("ai", "Namaste! Kurta ko barema kei jijnasa cha?"))
        self.assertEqual(FollowUp.objects.get().status, FollowUp.SENT)
        self.assertEqual(sales.send_followups(), 0)

    def test_follow_up_cancelled_when_customer_writes(self):
        with llm_returns(answer(stage="interested"))[0]:
            self.customer_says("kurta?")
        fu = FollowUp.objects.get()
        Message.objects.create(conversation=self.conv(), direction="in", text="ok later", sent_at=timezone.now() + timedelta(seconds=1))
        FollowUp.objects.update(due_at=timezone.now() - timedelta(minutes=1))
        sales.send_followups()
        fu.refresh_from_db()
        self.assertEqual(fu.status, FollowUp.CANCELLED)

    def test_messenger_follow_up_respects_24_hour_window(self):
        ch = ChannelAccount.objects.create(workspace=self.ws, provider="messenger", name="Page", is_demo=True, status="active")
        with llm_returns(answer(stage="interested"))[0]:
            msg = ingest_message(ch, IncomingMessage(external_thread_id="m1", contact_external_id="m1", contact_name="A",
                                                     text="price?", external_message_id="mx", sent_at=timezone.now()))
            engine.process_incoming(msg.id)
        fu = FollowUp.objects.get(conversation__external_thread_id="m1")
        self.assertLessEqual(fu.due_at, timezone.now() + timedelta(hours=22, minutes=1))
        Message.objects.filter(conversation=fu.conversation).update(sent_at=timezone.now() - timedelta(hours=30))
        FollowUp.objects.update(created_at=timezone.now() - timedelta(hours=29), due_at=timezone.now())
        sales.send_followups()
        fu.refresh_from_db()
        self.assertEqual(fu.status, FollowUp.SKIPPED)

    def test_done_stage_cancels_pending_follow_up(self):
        with llm_returns(answer(stage="interested"))[0]:
            self.customer_says("kurta?")
        with llm_returns(answer(stage="none"))[0]:
            self.customer_says("no thanks")
        self.assertEqual(FollowUp.objects.filter(status=FollowUp.PENDING).count(), 0)


def add_file(msg, kind, mime, data=b"x" * 100):
    att = Attachment.objects.create(workspace=msg.conversation.workspace, message=msg, kind=kind, mime=mime,
                                    status=Attachment.READY, size=len(data), extension=".bin")
    att.file.save("x.bin", ContentFile(data), save=True)
    return att


class VoiceNoteTests(SalesBase):
    def test_voice_note_is_transcribed_and_answered(self):
        self.n += 1
        msg = ingest_message(self.channel, IncomingMessage(external_thread_id="t1", contact_external_id="t1", contact_name="Sita",
                                                           text="", external_message_id="v1", sent_at=timezone.now()))
        add_file(msg, Attachment.VOICE, "audio/ogg")
        patch, calls = llm_returns("कुर्ता को मूल्य कति हो?", answer(reply="Cotton kurta Rs 1,800 ho 🙏", stage="browsing"))
        with patch:
            engine.process_incoming(msg.id)
        att = Attachment.objects.get()
        self.assertEqual(att.transcript, "कुर्ता को मूल्य कति हो?")
        audio_part = calls[0][0]["content"][1]
        self.assertEqual(audio_part["type"], "input_audio")
        self.assertIn("[voice message] कुर्ता को मूल्य कति हो?", calls[1][-1]["content"])
        self.assertEqual(self.outgoing()[-1][1], "Cotton kurta Rs 1,800 ho 🙏")

    def test_voice_notes_off_skips_transcription(self):
        self.cfg.voice_notes = False
        self.cfg.save()
        msg = ingest_message(self.channel, IncomingMessage(external_thread_id="t1", contact_external_id="t1", contact_name="Sita",
                                                           text="", external_message_id="v2", sent_at=timezone.now()))
        add_file(msg, Attachment.VOICE, "audio/ogg")
        with llm_returns(answer(reply="Hello"))[0]:
            engine.process_incoming(msg.id)
        self.assertEqual(Attachment.objects.get().transcript, "")


class PaymentScreenshotTests(SalesBase):
    def setUp(self):
        super().setUp()
        self.cfg.bot_mode = self.cfg.BOT_OFF
        self.cfg.save()
        shop = ShopSettings.for_workspace(self.ws)
        shop.payment_receivers = "Sita Fashion Store\n9800000000"
        shop.save()
        self.customer_says("hello")
        from commerce import services
        self.order = services.save_order(self.ws, {"items": [{"product_id": self.kurta.id, "variant": "M", "quantity": 1}],
                                                   "delivery_charge": Decimal("100"), "payment_method": "bank",
                                                   "recipient_name": "Sita", "recipient_phone": "9841234567",
                                                   "address": "Baneshwor", "city": "Kathmandu", "conversation": self.conv()})

    def screenshot(self, n=1, **note):
        read = {"is_payment": True, "app": "esewa", "amount": 1900, "currency": "NPR", "txn_id": "0ABC123",
                "date_time": timezone.localdate().strftime("%Y-%m-%d") + " 10:15", "status": "Success",
                "receiver": "Sita Fashion Store", "sender": "Sita", "edit_signs": [], "description": "", **note}
        msg = ingest_message(self.channel, IncomingMessage(external_thread_id="t1", contact_external_id="t1", contact_name="Sita",
                                                           text="", external_message_id=f"img{n}", sent_at=timezone.now()))
        add_file(msg, Attachment.IMAGE, "image/png")
        patch, calls = llm_returns(read)
        with patch:
            engine.process_incoming(msg.id)
        return PaymentCheck.objects.order_by("-id").first(), calls

    def test_valid_screenshot_is_matched_but_not_marked_paid(self):
        check, calls = self.screenshot()
        self.assertEqual(calls[0][1]["content"][1]["type"], "image_url")
        self.assertEqual((check.verdict, check.order, check.status), ("valid", self.order, "pending"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "unpaid")  # staff confirm
        self.assertTrue(any("looks valid" in n for n in self.notes()))

    def test_staff_confirm_marks_paid(self):
        check, _ = self.screenshot()
        res = self.c.post(f"/api/payment-checks/{check.id}/confirm/", {}, format="json", HTTP_X_WORKSPACE_ID=str(self.ws.id))
        self.assertEqual(res.status_code, 200, res.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(res.data["status"], "confirmed")

    def test_reused_transaction_wrong_amount_and_receiver_are_suspicious(self):
        self.screenshot()
        check, _ = self.screenshot(n=2, amount=500, receiver="Someone Else")
        self.assertEqual(check.verdict, "suspicious")
        text = " ".join(check.reasons)
        self.assertIn("already sent before", text)
        self.assertIn("doesn't match any unpaid order", text)
        self.assertIn("isn't one of your accounts", text)

    def test_failed_status_and_old_date_are_suspicious(self):
        check, _ = self.screenshot(status="Failed", date_time="2020-01-01 10:00", txn_id="X9")
        self.assertEqual(check.verdict, "suspicious")

    def test_product_photo_is_described_not_checked(self):
        self.screenshot(is_payment=False, description="Photo of a red kurta")
        self.assertEqual(PaymentCheck.objects.count(), 0)
        self.assertEqual(Attachment.objects.order_by("-created_at").first().ai_note["description"], "Photo of a red kurta")


class AutoShipTests(SalesBase):
    def test_paid_order_books_default_courier(self):
        shop = ShopSettings.for_workspace(self.ws)
        shop.auto_ship, shop.default_courier = "paid", "ncm"
        shop.secrets = {"ncm_token": "tok"}
        shop.save()
        from commerce import services
        order = services.save_order(self.ws, {"items": [{"product_id": self.kurta.id, "variant": "M", "quantity": 1}],
                                              "recipient_name": "Sita", "recipient_phone": "9841234567", "address": "Baneshwor",
                                              "city": "Kathmandu", "district": "Kathmandu", "payment_method": "khalti"})

        class R:
            def __init__(self, data):
                self.status_code, self._d, self.text = 200, data, ""

            def json(self):
                return self._d

        def request(method, url, **kw):
            return R({"orderid": 777} if "create" in url else {"trackid": "TRK777"})
        with mock.patch("commerce.delivery.requests.request", side_effect=request):
            services.mark_paid(order, via="Khalti")
        order.refresh_from_db()
        self.assertEqual((order.status, order.courier, order.tracking_id), ("shipped", "ncm", "TRK777"))

    def test_auto_ship_off_by_default(self):
        from commerce import services
        order = services.save_order(self.ws, {"items": [{"product_id": self.kurta.id, "variant": "M", "quantity": 1}],
                                              "payment_method": "cod"})
        services.set_status(order, "confirmed")
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")


@override_settings(OPENROUTER_API_KEY="test-key")
class ReportTests(SalesBase):
    def test_report_counts_ai_work(self):
        Booking.objects.create(workspace=self.ws, name="Ram", starts_at=timezone.now() + timedelta(hours=5), source="ai")
        res = self.c.get("/api/ai/report/?hours=12", HTTP_X_WORKSPACE_ID=str(self.ws.id))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["visits"], 1)
        self.assertEqual(res.data["upcoming_visits"], 1)

    def test_settings_round_trip(self):
        res = self.c.put("/api/ai/settings/", {"sales_orders": True, "booking_label": "Counselling session",
                                                "followup_enabled": True, "followup_hours": 5}, format="json",
                         HTTP_X_WORKSPACE_ID=str(self.ws.id))
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["booking_label"], res.data["followup_hours"]), ("Counselling session", 5))
        res = self.c.put("/api/ai/settings/", {"followup_hours": 99}, format="json", HTTP_X_WORKSPACE_ID=str(self.ws.id))
        self.assertEqual(res.status_code, 400)


class AbuseLimitTests(SalesBase):
    def test_too_many_ai_orders_in_one_chat_hands_over(self):
        self.customer_says("hi")
        conv = self.conv()
        for i in range(sales.MAX_AI_ORDERS_PER_CHAT_DAY):
            Order.objects.create(workspace=self.ws, number=f"#X{i}", conversation=conv, source="ai")
        order = {"items": [{"product_id": self.kurta.id, "option": "M", "quantity": 1}], "name": "Sita Sharma",
                 "phone": "9841234567", "address": "Baneshwor", "city": "Kathmandu", "district": "Kathmandu", "payment": "cod"}
        with llm_returns(answer(reply="Here is your order", action="propose_order", order=order))[0]:
            self.customer_says("one more order")
        self.assertNotIn("order_draft", self.conv().meta)
        self.assertTrue(self.conv().meta.get("bot_paused"))
        self.assertTrue(any("AI handed this conversation" in n for n in self.notes()))


class WebhookFailClosedTests(SalesBase):
    def test_providers_without_signature_check_reject_webhooks(self):
        from integrations.providers.base import BaseProvider
        self.assertFalse(BaseProvider.validate_webhook(mock.Mock(), None))
