"""Plan catalog: the single source of truth for pricing, limits and features.

The pricing page, the billing page and every limit check read from here.
Prices are per month; yearly billing is YEARLY_DISCOUNT off (paid up front).
"""
from decimal import ROUND_HALF_UP, Decimal

YEARLY_DISCOUNT = Decimal("0.20")
TRIAL_PLAN = "pro"
TRIAL_DAYS = 14

# Feature flags (keys used by the API and the UI)
F_TAGS = "tags"
F_CANNED = "canned_replies"
F_NOTES = "internal_notes"
F_ANALYTICS = "analytics"
F_SUPERVISOR = "supervisor_role"
F_AGENT_SCOPE = "agent_visibility"  # restrict agents to their own conversations
F_EXPORT = "csv_export"
F_API = "api_access"
F_PRIORITY = "priority_support"
F_PUBLISH = "social_publishing"
F_SCHEDULE = "scheduled_posts"
F_AI = "ai_assist"            # AI reply suggestions, rewrite, summaries, captions, auto-tagging
F_AUTOMATIONS = "automations"  # keyword / welcome / away rules and comment-to-DM
F_AI_BOT = "ai_chatbot"        # 24/7 AI chatbot that answers customers, with human handoff
F_AUDIT = "audit_log"         # who-did-what activity log
F_ORDERS = "orders"            # catalog, orders from chat, payment links, customer profiles
F_COURIERS = "courier_integrations"  # book Nepal Can Move / Pathao deliveries from an order
F_BROADCASTS = "broadcasts"    # WhatsApp template campaigns, Telegram/Viber/Messenger broadcasts
F_CSAT = "csat"                # satisfaction surveys + response-time targets
F_WHITE_LABEL = "white_label"  # your brand name, logo and colour; hide "Powered by"

FEATURE_LABELS = {
    F_AI: "AI reply suggestions, summaries & captions",
    F_AUTOMATIONS: "Automations: keyword, welcome & away replies, comment-to-DM",
    F_AI_BOT: "24/7 AI chatbot with human handoff",
    F_AUDIT: "Activity log (audit trail)",
    F_ORDERS: "Orders, products & Khalti/eSewa payment links",
    F_COURIERS: "Courier booking & tracking (Nepal Can Move, Pathao)",
    F_BROADCASTS: "Broadcasts (WhatsApp templates, Telegram, Viber, Messenger)",
    F_CSAT: "Customer satisfaction (CSAT) surveys & response-time targets",
    F_WHITE_LABEL: "White-label: your logo, colours & brand name",
    F_PUBLISH: "Post to Facebook, Instagram, YouTube & TikTok",
    F_SCHEDULE: "Scheduled posts & content calendar",
    F_TAGS: "Conversation tags",
    F_CANNED: "Saved replies",
    F_NOTES: "Internal notes",
    F_ANALYTICS: "Analytics dashboard",
    F_SUPERVISOR: "Supervisor role",
    F_AGENT_SCOPE: "Agent visibility controls",
    F_EXPORT: "CSV export",
    F_API: "API access",
    F_PRIORITY: "Priority support",
}

PLANS = {
    "free": {
        "name": "Free",
        "tagline": "Try a unified inbox with your first channels.",
        "price": {"NPR": 0, "USD": 0},
        "channels": 2,
        "seats": 1,
        "history_days": 30,
        "ai_credits": 50,
        "features": [F_AI],
    },
    "starter": {
        "name": "Starter",
        "tagline": "For solo sellers and small shops.",
        "price": {"NPR": 1499, "USD": 12},
        "channels": 4,
        "seats": 2,
        "history_days": 365,
        "ai_credits": 500,
        "features": [F_AI, F_AUTOMATIONS, F_ORDERS, F_PUBLISH, F_TAGS, F_CANNED],
    },
    "pro": {
        "name": "Pro",
        "tagline": "For growing teams handling daily conversations.",
        "price": {"NPR": 3999, "USD": 29},
        "channels": 10,
        "seats": 6,
        "history_days": None,  # unlimited
        "ai_credits": 3000,
        "features": [F_AI, F_AUTOMATIONS, F_AI_BOT, F_ORDERS, F_COURIERS, F_BROADCASTS, F_CSAT, F_PUBLISH, F_SCHEDULE, F_TAGS,
                     F_CANNED, F_NOTES, F_ANALYTICS, F_SUPERVISOR],
        "popular": True,
    },
    "business": {
        "name": "Business",
        "tagline": "For support teams with multiple brands.",
        "price": {"NPR": 8999, "USD": 69},
        "channels": 25,
        "seats": 15,
        "history_days": None,
        "ai_credits": 10000,
        "features": [F_AI, F_AUTOMATIONS, F_AI_BOT, F_ORDERS, F_COURIERS, F_BROADCASTS, F_CSAT, F_WHITE_LABEL, F_PUBLISH,
                     F_SCHEDULE, F_TAGS, F_CANNED, F_NOTES, F_ANALYTICS, F_SUPERVISOR, F_AGENT_SCOPE, F_AUDIT,
                     F_EXPORT, F_API, F_PRIORITY],
    },
    "enterprise": {
        "name": "Enterprise",
        "tagline": "Custom limits, onboarding and SLA.",
        "price": None,  # contact sales
        "channels": 1000,
        "seats": 1000,
        "history_days": None,
        "ai_credits": 50000,
        "features": list(FEATURE_LABELS),
    },
}
PAID_PLANS = ["starter", "pro", "business"]
EXTRA_SEAT_PRICE = {"NPR": 499, "USD": 5}  # per seat per month
CURRENCIES = ["NPR", "USD"]


def get_plan(key):
    return PLANS.get(key) or PLANS["free"]


def price_for(plan_key, cycle, currency, extra_seats=0):
    """Total price for one billing period, as a Decimal with 2 places."""
    plan = get_plan(plan_key)
    if not plan["price"]:
        raise ValueError("This plan has no public price.")
    monthly = Decimal(plan["price"][currency]) + Decimal(EXTRA_SEAT_PRICE[currency]) * extra_seats
    total = monthly * 12 * (1 - YEARLY_DISCOUNT) if cycle == "yearly" else monthly
    return total.quantize(Decimal("1") if currency == "NPR" else Decimal("0.01"), rounding=ROUND_HALF_UP)


def public_catalog():
    out = []
    for key, p in PLANS.items():
        prices = None
        if p["price"] is not None:
            prices = {
                cur: {"monthly": float(price_for(key, "monthly", cur)),
                      "yearly": float(price_for(key, "yearly", cur)),
                      "yearly_per_month": float((price_for(key, "yearly", cur) / 12).quantize(Decimal("0.01")))}
                for cur in CURRENCIES
            }
        out.append({
            "key": key, "name": p["name"], "tagline": p["tagline"], "prices": prices,
            "channels": p["channels"], "seats": p["seats"], "history_days": p["history_days"],
            "ai_credits": p["ai_credits"],
            "features": p["features"], "popular": p.get("popular", False),
        })
    return {
        "plans": out,
        "feature_labels": FEATURE_LABELS,
        "extra_seat": EXTRA_SEAT_PRICE,
        "yearly_discount": float(YEARLY_DISCOUNT),
        "trial_days": TRIAL_DAYS,
        "trial_plan": TRIAL_PLAN,
    }
