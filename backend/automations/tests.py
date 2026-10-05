import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Workspace
from inbox.models import Conversation, Message
from inbox.services import ingest_message
from integrations.models import ChannelAccount
from integrations.providers import IncomingMessage
from integrations.providers.meta import MetaBaseProvider

from . import comments, engine
from .models import AIUsage, AssistantSettings, KnowledgeItem, ProcessedComment, Rule

PASSWORD = "Kathmandu-Blue-42"


def register(client, email="owner@example.com"):
    res = client.post("/api/auth/register/", {"name": "Owner One", "email": email, "password": PASSWORD}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")


def llm_returns(*answers):
    """Patch the OpenRouter call; each call returns the next answer (dicts are sent as JSON)."""
    seq = [json.dumps(a) if isinstance(a, dict) else a for a in answers]
    calls = []

    def fake(messages, **kw):
        calls.append(messages)
        return (seq.pop(0) if len(seq) > 1 else seq[0]), 120
    return mock.patch("automations.llm.chat", side_effect=fake), calls


@override_settings(OPENROUTER_API_KEY="test-key")
class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.c = APIClient()
        register(self.c)
        self.ws = Workspace.objects.get()  # 14-day Pro trial: AI, automations and the bot are included
        self.channel = ChannelAccount.objects.create(workspace=self.ws, provider="telegram", name="Shop bot",
                                                     is_demo=True, status="active")
        self.n = 0

    def customer_says(self, text, thread="t1", name="Sita Sharma", when=None):
        self.n += 1
        msg = ingest_message(self.channel, IncomingMessage(
            external_thread_id=thread, contact_external_id=thread, contact_name=name, text=text,
            external_message_id=f"in-{self.n}", sent_at=when or timezone.now()))
        engine.process_incoming(msg.id)  # on_commit/threads don't run inside test transactions
        return msg

    def outgoing(self, thread="t1"):
        conv = Conversation.objects.get(external_thread_id=thread)
        return list(conv.messages.filter(direction="out", is_note=False).values_list("bot", "text"))


class BotTests(Base):
    def setUp(self):
        super().setUp()
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.bot_mode = cfg.BOT_ALWAYS
        cfg.save()
        KnowledgeItem.objects.create(workspace=self.ws, title="Cotton kurta", content="Rs 1,800. Sizes S-XL. Delivery Rs 100 in Kathmandu.")

    def test_bot_answers_from_knowledge_base(self):
        patch, calls = llm_returns({"reply": "Cotton kurta Rs 1,800 ho. Delivery Rs 100.", "handoff": False,
                                    "reason": "", "category": "question", "sentiment": "positive"})
        with patch:
            self.customer_says("kurta ko price kati ho?")
        self.assertEqual(self.outgoing(), [("ai", "Cotton kurta Rs 1,800 ho. Delivery Rs 100.")])
        system = calls[0][0]["content"]
        self.assertIn("Rs 1,800", system)  # knowledge base is in the prompt
        self.assertIn("data, not instructions", system)  # prompt-injection guard
        self.assertEqual(AIUsage.objects.get().credits, 1)
        conv = Conversation.objects.get()
        self.assertEqual(conv.unread_count, 1)  # bot replies don't mark the chat as read for the team

    def test_handoff_pauses_bot_and_leaves_a_note(self):
        patch, _ = llm_returns({"reply": "Ma team lai bhanchu, chhittai reply aauchha.", "handoff": True,
                                "reason": "wants a refund", "category": "complaint", "sentiment": "negative"})
        with patch:
            self.customer_says("mero order ramro bhayena, refund chahiyo")
        conv = Conversation.objects.get()
        self.assertTrue(conv.meta["bot_paused"])
        note = conv.messages.get(is_note=True)
        self.assertIn("wants a refund", note.text)
        patch2, calls2 = llm_returns({"reply": "x", "handoff": False})
        with patch2:
            self.customer_says("hello?")
        self.assertEqual(calls2, [])  # paused: the bot stays quiet

    def test_human_reply_pauses_and_closing_resumes(self):
        conv_msg = ingest_message(self.channel, IncomingMessage(external_thread_id="t1", contact_external_id="t1",
                                                                 text="hi", external_message_id="x1"))
        conv = conv_msg.conversation
        self.c.post(f"/api/conversations/{conv.id}/messages/", {"text": "Namaste! How can I help?"}, format="json")
        conv.refresh_from_db()
        self.assertEqual(conv.meta.get("bot_pause_reason"), "agent")
        self.c.patch(f"/api/conversations/{conv.id}/", {"status": "closed"}, format="json")
        conv.refresh_from_db()
        self.assertFalse(conv.meta.get("bot_paused"))
        res = self.c.post(f"/api/conversations/{conv.id}/bot/", {"paused": True}, format="json")
        self.assertTrue(res.data["ai"]["bot_paused"])

    def test_ignores_old_history_and_answered_messages(self):
        patch, calls = llm_returns({"reply": "x", "handoff": False})
        with patch:
            self.customer_says("old message", when=timezone.now() - timedelta(hours=3))
        self.assertEqual(calls, [])

    def test_loop_guard(self):
        patch, calls = llm_returns({"reply": "Auto answer", "handoff": False})
        with patch:
            for i in range(engine.LOOP_MAX + 3):  # a bot on the other side keeps writing
                self.customer_says(f"message {i}")
        self.assertEqual(len(calls), engine.LOOP_MAX)  # we stop answering after LOOP_MAX automatic replies

    def test_after_hours_mode(self):
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.bot_mode = cfg.BOT_AFTER_HOURS
        cfg.hours = {d: {"on": True, "start": "00:00", "end": "23:59"} for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
        cfg.save()
        patch, calls = llm_returns({"reply": "x", "handoff": False})
        with patch:
            self.customer_says("hello")
        self.assertEqual(calls, [])  # open now -> humans answer

    def test_out_of_credits(self):
        AIUsage.objects.create(workspace=self.ws, month=timezone.localdate().replace(day=1), credits=3000)
        patch, calls = llm_returns({"reply": "x", "handoff": False})
        with patch:
            self.customer_says("hello")
        self.assertEqual(calls, [])
        conv = Conversation.objects.get()
        self.assertEqual(self.c.post("/api/ai/suggest/", {"conversation_id": str(conv.id)}, format="json").status_code, 402)


class RuleTests(Base):
    def test_keyword_rule_replies_tags_and_stops_bot(self):
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.bot_mode = cfg.BOT_ALWAYS
        cfg.save()
        tag = self.c.post("/api/tags/", {"name": "Price", "color": "#16a34a"}, format="json").data
        res = self.c.post("/api/automations/rules/", {
            "name": "Price", "trigger": "keyword", "keywords": ["price", "kati"],
            "reply_text": "Hi {name}! Our price list: omni.shop/prices", "add_tag_id": tag["id"]}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        patch, calls = llm_returns({"reply": "x", "handoff": False})
        with patch:
            self.customer_says("PRICE kati ho?")
        self.assertEqual(self.outgoing(), [("rule", "Hi Sita! Our price list: omni.shop/prices")])
        self.assertEqual(calls, [])
        self.assertEqual(list(Conversation.objects.get().tags.values_list("name", flat=True)), ["Price"])
        self.assertEqual(Rule.objects.get().run_count, 1)

    def test_welcome_once_and_away_every_12h(self):
        Rule.objects.create(workspace=self.ws, name="Hi", trigger="welcome", reply_text="Welcome to our shop!")
        Rule.objects.create(workspace=self.ws, name="Away", trigger="away", reply_text="We're closed, back at 10am.")
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.hours = {d: {"on": False, "start": "10:00", "end": "18:00"} for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
        cfg.save()
        self.customer_says("hello")
        self.customer_says("anyone there?")
        texts = [t for _, t in self.outgoing()]
        self.assertEqual(texts, ["Welcome to our shop!", "We're closed, back at 10am."])

    def test_validation_permissions_and_plan(self):
        bad = self.c.post("/api/automations/rules/", {"name": "x", "trigger": "keyword", "reply_text": "hi"}, format="json")
        self.assertIn("keywords", bad.data)
        bad2 = self.c.post("/api/automations/rules/", {"name": "x", "trigger": "comment", "reply_text": "hi",
                                                         "channel_id": str(self.channel.id)}, format="json")
        self.assertIn("channel_id", bad2.data)  # demo Telegram can't have comments
        Workspace.objects.update(plan="free", trial_ends_at=None)
        res = self.c.post("/api/automations/rules/", {"name": "x", "trigger": "welcome", "reply_text": "hi"}, format="json")
        self.assertEqual(res.status_code, 402)
        self.assertEqual(self.c.put("/api/ai/settings/", {"bot_mode": "always"}, format="json").status_code, 402)


class AIEndpointTests(Base):
    def test_suggest_rewrite_summary_caption_playground(self):
        msg = ingest_message(self.channel, IncomingMessage(external_thread_id="t1", contact_external_id="t1",
                                                            text="delivery pokhara ma huncha?", external_message_id="a"))
        cid = str(msg.conversation_id)
        with llm_returns({"reply": "Huncha! Pokhara delivery [price].", "confidence": "low", "missing": "Pokhara delivery price"})[0]:
            r = self.c.post("/api/ai/suggest/", {"conversation_id": cid, "instruction": "be brief"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["missing"], "Pokhara delivery price")
        with llm_returns("Thank you so much for your order!")[0]:
            r = self.c.post("/api/ai/rewrite/", {"text": "thx for order", "mode": "friendlier"}, format="json")
        self.assertEqual(r.data["text"], "Thank you so much for your order!")
        with llm_returns({"summary": "Asks about delivery to Pokhara.", "category": "question", "sentiment": "neutral",
                          "next_step": "Share the delivery charge."})[0]:
            r = self.c.post("/api/ai/summary/", {"conversation_id": cid}, format="json")
        self.assertEqual(r.data["category"], "question")
        conv = self.c.get(f"/api/conversations/{cid}/").data
        self.assertEqual(conv["ai"]["summary"]["summary"], "Asks about delivery to Pokhara.")
        with llm_returns({"captions": {"facebook": "Dashain sale!", "instagram": "Dashain sale ✨ #dashain"}, "title": ""})[0]:
            r = self.c.post("/api/ai/caption/", {"brief": "Dashain sale 20% off", "platforms": ["facebook", "instagram"]},
                            format="json")
        self.assertEqual(set(r.data["captions"]), {"facebook", "instagram"})
        with llm_returns({"reply": "Namaste!", "handoff": False, "category": "question", "sentiment": "neutral"})[0]:
            r = self.c.post("/api/ai/playground/", {"message": "hello"}, format="json")
        self.assertEqual(r.data["reply"], "Namaste!")
        s = self.c.get("/api/ai/settings/").data
        self.assertEqual(s["credits"]["used"], 5)
        self.assertEqual(s["model"], "openai/gpt-4o")

    def test_ai_errors_are_friendly(self):
        from .llm import AIError
        msg = ingest_message(self.channel, IncomingMessage(external_thread_id="t1", contact_external_id="t1",
                                                            text="hi", external_message_id="a"))
        with mock.patch("automations.llm.chat", side_effect=AIError("The OpenRouter API key is invalid.")):
            r = self.c.post("/api/ai/suggest/", {"conversation_id": str(msg.conversation_id)}, format="json")
        self.assertEqual(r.status_code, 503)
        self.assertIn("API key", r.data["detail"])
        self.assertEqual(self.c.post("/api/ai/suggest/", {"conversation_id": "nope"}, format="json").status_code, 404)

    @override_settings(OPENROUTER_API_KEY="")
    def test_not_configured(self):
        r = self.c.post("/api/ai/rewrite/", {"text": "hi", "mode": "improve"}, format="json")
        self.assertEqual(r.status_code, 503)
        self.assertIn("OPENROUTER_API_KEY", r.data["detail"])

    def test_auto_tag(self):
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.auto_tag = True
        cfg.save()
        with llm_returns({"category": "order", "sentiment": "positive"})[0]:
            self.customer_says("2 ota kurta order garna milcha?")
        conv = Conversation.objects.get()
        self.assertEqual(conv.meta["ai_category"], "order")
        self.assertEqual(list(conv.tags.values_list("name", flat=True)), ["Order"])

    def test_agents_cannot_change_settings(self):
        inv = self.c.post("/api/team/", {"email": "agent@example.com", "role": "agent"}, format="json").data
        APIClient().post(f"/api/invites/{inv['url'].rsplit('/', 1)[1]}/", {"name": "Agent A", "password": PASSWORD}, format="json")
        agent = APIClient()
        agent.credentials(HTTP_AUTHORIZATION="Bearer " + agent.post(
            "/api/auth/login/", {"email": "agent@example.com", "password": PASSWORD}, format="json").data["access"])
        self.assertEqual(agent.put("/api/ai/settings/", {"about": "x"}, format="json").status_code, 403)
        self.assertEqual(agent.post("/api/ai/knowledge/", {"title": "x", "content": "y"}, format="json").status_code, 403)
        self.assertEqual(agent.get("/api/ai/settings/").status_code, 200)


class CommentTests(Base):
    def setUp(self):
        super().setUp()
        self.page = ChannelAccount.objects.create(
            workspace=self.ws, provider="messenger", name="My Page", status="active",
            credentials={"page_id": "PAGE1", "page_access_token": "PT", "app_secret": "s"})
        self.rule = Rule.objects.create(workspace=self.ws, name="Price comments", trigger="comment", channel=self.page,
                                        keywords=["price", "kati"], reply_text="Hi {name}! Price is Rs 1,800. DM us to order.",
                                        public_reply_text="Sent you a DM, {name}!")
        self.graph_calls = []

    def graph(self):
        def http(method, url, **kw):
            self.graph_calls.append((method, url.split("graph.facebook.com/")[-1].split("/", 1)[-1], kw.get("json")))
            return {"message_id": "m1", "id": "c1"}
        return mock.patch.object(MetaBaseProvider, "http", staticmethod(http))

    def webhook_body(self, comment_id, text, from_id="USER9", name="Ram Thapa"):
        return json.dumps({"object": "page", "entry": [{"id": "PAGE1", "changes": [{"field": "feed", "value": {
            "item": "comment", "verb": "add", "comment_id": comment_id, "post_id": "PAGE1_55", "message": text,
            "from": {"id": from_id, "name": name}, "created_time": int(timezone.now().timestamp()) + 5}}]}]}).encode()

    def test_comment_to_dm_via_webhook(self):
        with self.graph():
            self.assertEqual(comments.handle_webhook(self.page, self.webhook_body("C1", "price kati?")), 1)
            self.assertEqual(comments.handle_webhook(self.page, self.webhook_body("C1", "price kati?")), 0)  # duplicate
            self.assertEqual(comments.handle_webhook(self.page, self.webhook_body("C2", "nice photo")), 0)  # no keyword
            self.assertEqual(comments.handle_webhook(self.page, self.webhook_body("C3", "price?", from_id="PAGE1")), 0)
        dm, public = self.graph_calls
        self.assertEqual(dm[1], "me/messages")
        self.assertEqual(dm[2]["recipient"], {"comment_id": "C1"})
        self.assertEqual(dm[2]["message"]["text"], "Hi Ram! Price is Rs 1,800. DM us to order.")
        self.assertEqual(public[1], "C1/comments")
        self.assertEqual(Rule.objects.get().run_count, 1)

    def test_polling_baselines_first_then_answers_new(self):
        feed = {"data": [{"id": "PAGE1_55", "comments": {"data": [
            {"id": "OLD", "message": "price?", "from": {"id": "U1", "name": "Old Person"},
             "created_time": timezone.now().isoformat()}]}}]}
        with mock.patch.object(MetaBaseProvider, "http", staticmethod(lambda *a, **k: feed)):
            self.assertEqual(comments.poll_channel(self.page), 0)  # first pass: remember existing comments only
        self.assertTrue(ProcessedComment.objects.filter(comment_id="OLD").exists())
        feed["data"][0]["comments"]["data"].append(
            {"id": "NEW", "message": "kati parcha?", "from": {"id": "U2", "name": "Gita"},
             "created_time": (timezone.now() + timedelta(seconds=5)).isoformat()})

        def http(method, url, **kw):
            self.graph_calls.append((method, url, kw.get("json")))
            return feed if method == "GET" else {"message_id": "m"}
        with mock.patch.object(MetaBaseProvider, "http", staticmethod(http)):
            self.page.refresh_from_db()
            self.assertEqual(comments.poll_channel(self.page), 1)
        posted = [c for c in self.graph_calls if c[0] == "POST"]
        self.assertEqual(posted[0][2]["recipient"], {"comment_id": "NEW"})

    def test_comments_before_rule_was_created_are_ignored(self):
        Rule.objects.update(created_at=timezone.now() + timedelta(hours=1))
        with self.graph():
            self.assertEqual(comments.handle_webhook(self.page, self.webhook_body("C9", "price")), 0)


class WebsiteWidgetProtectionTests(Base):
    """The public website chat protects the AI budget: message length, rate limits, per-visitor and daily AI caps."""

    def setUp(self):
        super().setUp()
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.bot_mode = cfg.BOT_ALWAYS
        cfg.save()
        self.channel = ChannelAccount.objects.create(
            workspace=self.ws, provider="website", name="Site", status="active",
            credentials={"title": "Chat", "max_chars": "300", "ai_per_visitor": "5", "ai_per_day": "50"})
        self.anon = APIClient()

    def session(self, client=None):
        return (client or self.anon).post(f"/api/widget/{self.channel.id}/session/", {}, format="json").data["token"]

    def send(self, token, text):
        return self.anon.post(f"/api/widget/{self.channel.id}/messages/", {"text": text}, format="json",
                              HTTP_X_VISITOR_TOKEN=token)

    def test_long_messages_and_floods_are_refused(self):
        self.assertEqual(self.anon.get(f"/api/widget/{self.channel.id}/").data["max_chars"], 300)
        token = self.session()
        with mock.patch("automations.engine.schedule"):
            r = self.send(token, "x" * 301)
            self.assertEqual(r.status_code, 400)
            self.assertIn("300 characters", r.data["detail"])
            codes = [self.send(token, f"hi {i}").status_code for i in range(9)]
        self.assertEqual(codes, [201] * 8 + [429])  # 8 messages a minute per visitor
        self.assertEqual(Message.objects.filter(direction="in").count(), 8)

    def test_new_visitor_ids_are_rate_limited_per_ip(self):
        codes = [APIClient().post(f"/api/widget/{self.channel.id}/session/", {}, format="json",
                                  HTTP_X_FORWARDED_FOR="203.0.113.9").status_code for _ in range(31)]
        self.assertEqual(codes[-1], 429)
        self.assertEqual(APIClient().post(f"/api/widget/{self.channel.id}/session/", {}, format="json",
                                          HTTP_X_FORWARDED_FOR="203.0.113.10").status_code, 200)  # other visitors fine

    def _ai_history(self, thread, n):
        conv = Conversation.objects.get(external_thread_id=thread)
        earlier = timezone.now() - timedelta(hours=1)  # inside the 24h budget, outside the loop guard window
        for i in range(n):
            Message.objects.create(conversation=conv, direction="out", bot="ai", text=f"answer {i}", status="sent", sent_at=earlier)

    def test_ai_stops_after_per_visitor_budget_and_team_takes_over(self):
        patch, calls = llm_returns({"reply": "Our Pro plan is Rs 3,999.", "handoff": False})
        with patch:
            self.customer_says("price?", thread="v1")
            self.assertEqual(len(calls), 1)
            self._ai_history("v1", 4)  # 5 AI replies today now
            self.customer_says("and yearly?", thread="v1")
        self.assertEqual(len(calls), 1)  # no second OpenRouter call
        conv = Conversation.objects.get(external_thread_id="v1")
        self.assertEqual(self.outgoing("v1")[-1][0], "rule")  # fixed "our team will reply" message, no AI
        self.assertEqual(conv.meta["bot_pause_reason"], "limit")
        self.assertIn("limit reached", conv.messages.filter(is_note=True).last().text)

    def test_daily_budget_for_the_whole_widget(self):
        patch, calls = llm_returns({"reply": "Hi!", "handoff": False})
        with patch:
            self.customer_says("hello", thread="old")
            self._ai_history("old", 49)  # 50 AI replies today on this widget
            self.customer_says("hello", thread="new-visitor")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.outgoing("new-visitor"), [("rule", AssistantSettings.for_workspace(self.ws).handoff_message)])

    def test_widget_prompt_is_smaller(self):
        patch, calls = llm_returns({"reply": "ok", "handoff": False})
        with patch as chat:
            self.customer_says("hi", thread="v2")
        self.assertEqual(chat.call_args.kwargs["max_tokens"], 350)


class SiteChatSetupTests(TestCase):
    def test_setup_command_creates_site_chat_and_public_endpoint_finds_it(self):
        from django.core.management import call_command
        cache.clear()
        c = APIClient()
        register(c, "founder@example.com")
        self.assertIsNone(APIClient().get("/api/widget/site/").data["channel"])
        call_command("setup_site_chat", email="founder@example.com", stdout=open("/dev/null", "w"))
        ch = ChannelAccount.objects.get(state__site_chat=True)
        self.assertEqual(APIClient().get("/api/widget/site/").data["channel"], str(ch.id))
        self.assertEqual(ch.credentials["max_chars"], "500")
        kb = " ".join(KnowledgeItem.objects.filter(workspace=ch.workspace).values_list("content", flat=True))
        self.assertIn("Rs 3,999", kb)  # prices come from billing/plans.py
        self.assertEqual(AssistantSettings.for_workspace(ch.workspace).bot_mode, "always")
        call_command("setup_site_chat", email="founder@example.com", stdout=open("/dev/null", "w"))  # re-run = refresh
        self.assertEqual(ChannelAccount.objects.filter(state__has_key="site_chat").count(), 1)
        self.assertEqual(KnowledgeItem.objects.filter(workspace=ch.workspace).count(), 8)
        # customers can't turn their own widget into the site chat through the API
        self.assertNotIn("state", c.get(f"/api/channels/{ch.id}/").data)
