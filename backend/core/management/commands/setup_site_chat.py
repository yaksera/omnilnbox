"""Set up the AI chat bubble on OmniInbox's own website (home, pricing, docs, contact pages).

    python manage.py setup_site_chat --email you@yourcompany.com

Creates (or updates) a workspace owned by that account with a "Website chat" channel, an AI assistant that
knows OmniInbox's features and prices, and safe usage limits. Visitor chats land in that workspace's inbox,
so your team can take over any conversation. Re-run it any time: it refreshes the knowledge (e.g. after a
price change) and keeps the conversations.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from automations.models import AssistantSettings, KnowledgeItem
from billing.plans import EXTRA_SEAT_PRICE, FEATURE_LABELS, PAID_PLANS, PLANS, TRIAL_DAYS, YEARLY_DISCOUNT
from core.models import Membership, Workspace
from integrations.models import ChannelAccount

KB_TAG = "[site] "  # knowledge entries this command owns (refreshed on every run)


def _money(n, cur):
    return f"Rs {n:,}" if cur == "NPR" else f"${n:,}"


def knowledge():
    plans = []
    for key in ["free", *PAID_PLANS, "enterprise"]:
        p = PLANS[key]
        price = ("free" if p["price"] and p["price"]["NPR"] == 0 else
                 f"{_money(p['price']['NPR'], 'NPR')} or {_money(p['price']['USD'], 'USD')} per month" if p["price"]
                 else "custom price (talk to our team)")
        feats = "; ".join(FEATURE_LABELS[f] for f in p["features"] if f in FEATURE_LABELS)
        plans.append(f"- {p['name']}: {price}. {p['channels'] if p['channels'] < 1000 else 'Unlimited'} channels, "
                     f"{p['seats'] if p['seats'] < 1000 else 'unlimited'} team seats, {p['ai_credits']:,} AI credits/month. "
                     f"Includes: {feats}.")
    yearly = int(YEARLY_DISCOUNT * 100)
    return [
        ("What OmniInbox is",
         "OmniInbox is a unified inbox for businesses, built in Kathmandu. Every customer message from WhatsApp, Instagram, "
         "Facebook Messenger, TikTok, Viber, Telegram, Discord, email (Gmail, Outlook, Zoho, any IMAP) and a website chat "
         "bubble arrives in one inbox, and the team replies from there; the reply goes back on the customer's own app. "
         "It also has a 24/7 AI chatbot, orders with Khalti/eSewa payment links, Nepal Can Move and Pathao delivery "
         "booking, social media publishing, broadcasts, team roles and analytics. Customers don't install anything."),
        ("Plans and prices",
         "Prices per month (pay in Nepali rupees or US dollars):\n" + "\n".join(plans) +
         f"\nYearly billing is {yearly}% cheaper. Extra team seats cost {_money(EXTRA_SEAT_PRICE['NPR'], 'NPR')} "
         f"({_money(EXTRA_SEAT_PRICE['USD'], 'USD')}) per seat per month. Full comparison: /pricing"),
        ("Free trial, payment and cancelling",
         f"Every new workspace gets a {TRIAL_DAYS}-day trial of the Pro plan, no card needed. Sign up at /register. "
         "Pay in NPR with Khalti or eSewa, or in USD by Visa/Mastercard. Plans are prepaid monthly or yearly and never "
         "renew automatically; if you don't renew you move to the Free plan and your data is kept. Upgrade any time from "
         "the Billing page."),
        ("Channels and what you need to connect them",
         "WhatsApp: official WhatsApp Business Platform (Cloud API) number via a Meta app (not the WhatsApp Business phone app). "
         "Facebook Messenger and Instagram: a Facebook Page / Instagram professional account and a Meta app. "
         "TikTok Business Messaging and Viber bots need approval from TikTok / a commercial Viber bot. "
         "Telegram: a bot from @BotFather (2 minutes). Website chat: paste one line of code. Email: an app password. "
         "Discord: a bot token. Most channels take under 10 minutes. Step-by-step guides with screenshots: /docs/channels"),
        ("AI chatbot and AI credits",
         "The AI answers customers 24/7 (or only outside business hours) in Nepali, Romanized Nepali or English, using only "
         "the business's own knowledge base. It hands the chat to the team for orders, payments, refunds, complaints or "
         "anything it doesn't know, and stops when an agent replies. It also suggests replies, rewrites/translates, "
         "summarises chats, labels conversations and writes social media captions. One AI credit = one AI action; "
         "credits reset every month. The 24/7 chatbot is on Pro and above; AI suggestions are on every plan."),
        ("Selling in chat: orders, payments, delivery",
         "Create orders from a chat in seconds, keep a product catalog with stock, send the order summary, and collect "
         "payment with Khalti or eSewa payment links (money goes straight to the business's own merchant account). "
         "Book Nepal Can Move or Pathao deliveries from the order; tracking updates automatically and customers get "
         "shipped/delivered messages. Orders are on Starter and above; courier booking on Pro and above."),
        ("Marketing: posts, broadcasts, comments",
         "Publish to a Facebook Page, Instagram, YouTube and TikTok at once, or schedule on a calendar (Pro). "
         "Broadcast offers to many customers on WhatsApp (approved templates), Viber, Telegram and Messenger (Pro). "
         "Comment-to-DM: someone comments \"price?\" on a post and automatically gets the details in their inbox."),
        ("Team, security and support",
         "Roles: Owner, Admin, Supervisor, Agent. Features: assign chats, internal notes, tags, saved replies, "
         "reply-time targets, satisfaction surveys, analytics, push notifications on phone and desktop, install as an app. "
         "Security: encrypted channel tokens, two-factor login, activity log (Business), isolated workspaces, HTTPS. "
         "Developers: REST API and webhooks (Business). Help center with setup guides: /docs. Contact the team: /contact."),
    ]


class Command(BaseCommand):
    help = "Create/refresh the AI chat bubble shown on OmniInbox's own marketing website."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Your OmniInbox login; you'll own the site-chat workspace.")
        parser.add_argument("--workspace", default="OmniInbox Website", help="Name of the workspace for site chats.")
        parser.add_argument("--color", default="#4f46e5")
        parser.add_argument("--max-chars", default="500", choices=["300", "500", "1000", "2000"])
        parser.add_argument("--ai-per-visitor", default="10", choices=["5", "10", "20", "50", "100"])
        parser.add_argument("--ai-per-day", default="300", choices=["50", "100", "300", "1000", "3000"])
        parser.add_argument("--disable", action="store_true", help="Hide the chat bubble from the website.")

    def handle(self, *args, **o):
        user = get_user_model().objects.filter(email__iexact=o["email"]).first()
        if not user:
            raise CommandError(f"No account with email {o['email']}. Sign up in the app first, then run this again.")
        channel = (ChannelAccount.objects.filter(provider="website", state__has_key="site_chat",
                                                 workspace__memberships__user=user, workspace__memberships__role="owner")
                   .select_related("workspace").first())
        if o["disable"]:
            if channel:
                channel.state = {**channel.state, "site_chat": False}
                channel.save(update_fields=["state"])
            cache.delete("omni:widget:site-channel")
            self.stdout.write(self.style.SUCCESS("Website chat bubble turned off."))
            return

        if channel:
            ws = channel.workspace
        else:
            ws = Workspace.objects.create(name=o["workspace"], slug=f"{slugify(o['workspace'])}-{user.pk}-site"[:140])
            Membership.objects.create(user=user, workspace=ws, role="owner")
        # Your own internal workspace: all features; marked internal so it isn't counted as a paying customer.
        ws.plan, ws.plan_expires_at, ws.trial_ends_at = "business", timezone.now() + timedelta(days=3650), None
        ws.is_internal = True
        ws.save(update_fields=["plan", "plan_expires_at", "trial_ends_at", "is_internal"])

        creds = {"title": "Chat with OmniInbox", "color": o["color"], "ask_contact": "optional",
                 "greeting": "Namaste! 👋 I'm Omni. Ask me anything about OmniInbox: channels, AI, pricing or setup.",
                 "max_chars": o["max_chars"], "ai_per_visitor": o["ai_per_visitor"], "ai_per_day": o["ai_per_day"]}
        if channel:
            channel.credentials = {**channel.credentials, **{k: creds[k] for k in ("max_chars", "ai_per_visitor", "ai_per_day")}}
            channel.status = ChannelAccount.STATUS_ACTIVE
            channel.state = {**channel.state, "site_chat": True}
            channel.save(update_fields=["credentials", "status", "state"])
        else:
            channel = ChannelAccount.objects.create(workspace=ws, provider="website", name="OmniInbox website",
                                                    credentials=creds, status=ChannelAccount.STATUS_ACTIVE,
                                                    state={"site_chat": True}, created_by=user)

        AssistantSettings.objects.update_or_create(workspace=ws, defaults={
            "business_name": "OmniInbox", "bot_name": "Omni", "tone": "friendly", "bot_mode": AssistantSettings.BOT_ALWAYS,
            "auto_tag": False,  # saves one AI call per new visitor
            "about": "OmniInbox is a unified inbox SaaS for businesses (made in Nepal): all customer chats from WhatsApp, "
                     "Instagram, Messenger, TikTok, Viber, Telegram, email and website chat in one place, plus an AI chatbot, "
                     "orders and payments, delivery booking and social publishing. You are chatting with visitors on the "
                     "OmniInbox website: help them understand the product and pricing and get started with the free trial. "
                     "Keep answers short (2-4 sentences). Share links as paths like /pricing, /register or /docs. "
                     "Only talk about OmniInbox: politely decline anything unrelated (general questions, homework, "
                     "writing essays or code, translating long texts) in one sentence.",
            "handoff_message": "Thanks! Someone from the OmniInbox team will reply here soon. "
                               "Leave your email or phone if you'd like us to contact you.",
        })
        KnowledgeItem.objects.filter(workspace=ws, title__startswith=KB_TAG).delete()
        for title, content in knowledge():
            KnowledgeItem.objects.create(workspace=ws, title=KB_TAG + title, content=content[:4000])
        cache.delete("omni:widget:site-channel")

        self.stdout.write(self.style.SUCCESS("Website chat is ready."))
        self.stdout.write(f"  Workspace: {ws.name} (switch to it from the menu under your initials in the app)")
        self.stdout.write(f"  Limits: {o['max_chars']} characters per message, {o['ai_per_visitor']} AI replies per visitor "
                          f"per day, {o['ai_per_day']} AI replies per day in total, 10,000 AI credits per month.")
        self.stdout.write("  Change limits: Channels → OmniInbox website → Edit. Edit answers: AI → Knowledge base.")
        self.stdout.write("  The chat bubble now appears on the home, pricing, docs and contact pages (refresh the page).")
