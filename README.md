# OmniInbox — unified inbox SaaS (MVP)

One web app to read and reply to messages from **WhatsApp, Instagram, Messenger, TikTok, Telegram, Discord, Gmail, Outlook and Zoho Mail** (plus any IMAP/SMTP mailbox).

- **Backend:** Django 5 + Django REST Framework, JWT auth, multi-tenant workspaces, encrypted channel credentials
- **Frontend:** Next.js 16 (App Router, TypeScript, Tailwind v4)
- **Demo mode:** one click loads sample conversations on all 9 platforms, so you can run it with no API keys

```
unified-inbox/
├── backend/                 Django REST API
│   ├── config/              settings, urls
│   ├── core/                users, workspaces (tenants), memberships, JWT auth, credential encryption
│   ├── integrations/        ChannelAccount model, webhooks, OAuth, workers
│   │   └── providers/       one connector per platform (whatsapp, instagram, messenger, tiktok,
│   │                        telegram, discord, gmail, outlook, zoho, imap) + demo
│   └── inbox/               Contact, Conversation, Message, reply service, tests
├── frontend/                Next.js app (landing, login/register, inbox, channels, settings)
└── docker-compose.yml       postgres + api + worker + discord listener + web
```

## Quick start (local, no Docker)

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                               # macOS/Linux: cp .env.example .env
python manage.py migrate
python manage.py createsuperuser                     # optional, for /admin
python manage.py runserver                           # http://localhost:8000
```

**Frontend** (Node 20+):

```bash
cd frontend
npm install
copy .env.example .env.local                         # BACKEND_URL=http://127.0.0.1:8000
npm run dev                                          # http://localhost:3000
```

The browser only talks to Next.js: requests to `/backend/*` are proxied to Django's `/api/*`
(see `frontend/next.config.ts`), so there is no CORS setup and it works on any port or host.
If you change `BACKEND_URL` or `next.config.ts`, restart `npm run dev`.

Open http://localhost:3000 → **Start free** → create an account → **Load demo data**.

**Workers** (needed for real channels):

```bash
python manage.py run_worker     # polls Gmail / Zoho / IMAP / Outlook + Telegram in polling mode
python manage.py run_discord    # keeps the Discord bot connected (Gateway)
```

## With Docker

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

## How it works

```
Platform ──webhook──▶ /api/webhooks/<channel_id>/ ─┐
Mailbox  ◀──poll──── run_worker ───────────────────┼─▶ ingest_message() ─▶ Contact / Conversation / Message
Discord  ──gateway─▶ run_discord ──────────────────┘
Agent reply ─▶ POST /api/conversations/<id>/messages/ ─▶ provider.send() ─▶ platform API
```

Every connector implements the same small interface in `integrations/providers/base.py`
(`verify`, `on_connect`, `webhook_challenge`, `validate_webhook`, `parse_webhook`, `poll`, `send`),
so adding a new platform is one file plus a line in `providers/__init__.py`.

Incoming messages are de-duplicated by the platform's message id, conversations re-open when a
customer writes again, and replies sent from the native apps (Messenger/Instagram "echoes", Discord bot
messages) are recorded as outgoing.

## Connecting real channels

Webhook-based channels need the backend reachable over **public HTTPS**. Locally, run a tunnel
(`ngrok http 8000` or `cloudflared tunnel --url http://localhost:8000`) and set `PUBLIC_BASE_URL` in
`backend/.env` to that URL. Each channel card in **Channels** shows its webhook URL and verify token.

| Channel | How it receives | What you need |
|---|---|---|
| **WhatsApp** | Webhook (Meta Cloud API) | Meta app with WhatsApp, Phone number ID, permanent token, app secret |
| **Messenger** | Webhook | Meta app + Facebook Page, Page access token (`pages_messaging`), app secret |
| **Instagram** | Webhook | IG professional account linked to a Page, `instagram_manage_messages`, app secret |
| **TikTok** *(beta)* | Webhook | Approved access to TikTok **Business Messaging API** (gated, region-limited) |
| **Telegram** | Polling (dev) or webhook (prod) | Bot token from @BotFather |
| **Discord** | Gateway (`run_discord`) | Bot token with the MESSAGE CONTENT intent turned on |
| **Gmail** | IMAP polling, SMTP send | Gmail address + App Password (needs 2-Step Verification) |
| **Zoho Mail** | IMAP polling, SMTP send | IMAP enabled + app-specific password, pick your region |
| **Outlook** | Microsoft Graph (OAuth) | Entra ID app: redirect `<PUBLIC_BASE_URL>/api/oauth/microsoft/callback/`, delegated `offline_access User.Read Mail.ReadWrite Mail.Send` |

Things to know about platform rules:

- **Meta (WhatsApp/Messenger/Instagram):** you can only send free-form replies within **24 hours** of the
  customer's last message. Outside that window WhatsApp needs an approved template message. Going live
  with other businesses' accounts requires Meta **App Review** and Business Verification.
- **TikTok:** the Business Messaging API is invite/approval-only and TikTok changes it often. The connector
  uses `business-api.tiktok.com/open_api/v1.3` with the `Access-Token` header. The send path is a field
  you can edit, and the webhook parser accepts several payload shapes. Check it against the docs you get
  when you're approved.
- **Gmail:** App Passwords are the quickest route. For a public SaaS, switch to the Gmail API with OAuth.
  The Outlook connector already shows how that flow works, and Google requires a security review for the
  restricted Gmail scopes.

## API reference (all under `/api/`, JWT `Authorization: Bearer <token>`)

| Method | Path | Purpose |
|---|---|---|
| POST | `auth/register/` · `auth/login/` · `auth/refresh/` | Sign up (creates a workspace), log in, refresh token |
| GET | `auth/me/` | Current user, workspace, role |
| PATCH | `workspace/` | Rename workspace |
| GET/POST | `team/` | List / add members |
| GET | `providers/` | Connector catalogue + form fields (drives the UI) |
| CRUD | `channels/` | Connected accounts (credentials write-only, masked on read) |
| POST | `channels/<id>/test/` · `sync/` · `oauth/start/` | Verify, poll now, start OAuth |
| POST / DELETE | `channels/demo/` · `channels/demo/clear/` | Load / remove demo data |
| GET | `conversations/?provider=&status=&unread=1&assigned=me&q=` | Unified conversation list |
| PATCH | `conversations/<id>/` | `status`, `assigned_to_id` |
| GET/POST | `conversations/<id>/messages/` | Read thread / send reply |
| POST | `conversations/<id>/read/` | Mark read |
| GET | `stats/` | Unread counts per platform |
| GET/POST | `webhooks/<channel_id>/` | Public webhook endpoint for the platforms |

Select a workspace with the `X-Workspace-Id` header (the default is the user's first workspace).

## AI & automations (AI page)

AI runs through **OpenRouter**. Put `OPENROUTER_API_KEY` in `backend/.env`; the model is `OPENROUTER_MODEL` (default `openai/gpt-4o`). Without a key, everything else keeps working and the AI buttons say how to set it up.

| Feature | Where | Plan |
|---|---|---|
| **Reply suggestions**: drafts an answer from the knowledge base and flags missing facts | Inbox → ✨ Suggest reply | All plans |
| **Rewrite / translate**: polish, shorter, friendlier, or translate to नेपाली, Romanized Nepali or English | Inbox → Rewrite | All plans |
| **Conversation summary** with category, sentiment and next step | Inbox → Summarize | All plans |
| **AI captions** for each platform, with hashtags and a YouTube title | Publish → Write with AI | All plans |
| **Auto-labels** new conversations (Order, Lead, Complaint, ...) | AI → AI assistant | All plans |
| **Keyword replies, welcome and away messages** (fixed text or AI-written), with tag and assign | AI → Automations | Starter+ |
| **Comment → DM**: comment on a FB/IG post → private message plus an optional public reply | AI → Automations | Starter+ |
| **24/7 AI chatbot** (always, or only outside business hours) with handoff to a human | AI → AI assistant | Pro+ |

**AI credits:** 1 credit = 1 AI action. Monthly allowance: Free 50, Starter 500, Pro 3,000, Business 10,000, Enterprise 50,000. It resets on the 1st of each month, and usage is shown on the AI page.

How the chatbot behaves:

- It answers only from "About the business", the **knowledge base** and your saved replies, in the customer's language. It never invents prices.
- It **hands over** to the team for orders, payments, refunds, complaints, or anything unknown. It then sends your handoff message, leaves an internal note with the reason, and pauses in that conversation.
- It **pauses** as soon as an agent replies. Closing the conversation or clicking "AI paused" in the thread turns it back on.
- Safety guards: it only answers fresh messages (never old history from a first sync), has a loop guard (max 4 automatic replies per conversation in 10 minutes), and treats customer text as data, not instructions.
- Automations and the bot run in a background thread after each incoming message, so webhooks return immediately.

**Comment → DM setup:** connect the Page as a Messenger channel (and/or Instagram), then create a Comment rule. New comments arrive by webhook: reconnecting a Messenger channel subscribes the Page to `feed`; in the Meta app, also subscribe the **Instagram `comments`** field. The worker also polls the 10 latest posts every cycle, which works even in Development mode. On first run it only records existing comments, and it answers only comments made after the rule was created, so old commenters never get spammed. Needs `pages_read_engagement`, `pages_manage_engagement` (public replies) and `pages_messaging`, or `instagram_manage_comments` for Instagram.

API: `ai/settings/`, `ai/knowledge/`, `ai/suggest/`, `ai/rewrite/`, `ai/summary/`, `ai/caption/`, `ai/playground/`, `automations/rules/`, `conversations/<id>/bot/`.

## Social publishing (Publish page)

Write one post and publish it to **Facebook Pages, Instagram, YouTube and TikTok**, either now or on a schedule. The Publish page has a composer with per-platform previews, caption counters and custom captions, plus a list of posts showing each platform's status, links, errors and a retry button, and a month calendar.

| Platform | How to connect | What it needs |
|---|---|---|
| Facebook Page | Publish → Accounts → paste a **System User token** (expiration: Never) | `pages_show_list`, `pages_manage_posts`, `pages_read_engagement` |
| Instagram | Added automatically for Instagram **professional** accounts linked to the Page | `instagram_basic`, `instagram_content_publish`; images must be **JPEG** |
| YouTube | "Sign in with YouTube" (Google OAuth) | `GOOGLE_CLIENT_ID/SECRET`, YouTube Data API v3 enabled; videos only |
| TikTok | "Sign in with TikTok" | `TIKTOK_CLIENT_KEY/SECRET`, Content Posting API; videos only |

Things to know:

- **Meta downloads your media from your server.** `PUBLIC_BASE_URL` must be public HTTPS (ngrok locally), just like webhooks. Media links are signed and expire after 24h, and nothing in `MEDIA_ROOT` is served publicly.
- **Scheduled posts are sent by the worker.** Keep `python manage.py run_worker` running. "Publish now" runs immediately in the background.
- **Approvals:** Meta needs App Review for `pages_manage_posts` / `instagram_content_publish` before you can post to Pages you don't admin. TikTok posts are **private (only you)** until TikTok audits your app. YouTube uploads from unverified Google projects are locked to **private** until Google's audit.
- Limits: images up to 8 MB, videos up to 500 MB. Plans: publishing on Starter+, scheduling on Pro+. Agents can save drafts, and supervisors, admins and owners can publish. Only admins and owners connect accounts.
- API: `publishing/config/`, `publishing/accounts/`, `publishing/accounts/facebook/`, `publishing/oauth/<youtube|tiktok>/start/`, `publishing/media/`, `publishing/posts/` (`?from=&to=` for calendar), `publishing/posts/<id>/`, `publishing/posts/<id>/retry/`.

## Help center, commerce and growth features

**Customer help center:** `/docs` (linked from the site header, footer, the app sidebar's **Help** button and the
**Setup** checklist). 37 step-by-step guides with screenshots live in `frontend/src/content/docs/*.ts`
(plain data: edit the text there) and the images in `frontend/public/docs-img/*.webp`.

| Area | Where in the app | What the customer needs |
|---|---|---|
| Orders, products, customers | Orders · Customers | nothing (Starter+) |
| Khalti / eSewa payment links | Orders → Shop settings → Online payments | their own Khalti / eSewa merchant keys |
| Nepal Can Move / Pathao | Orders → Shop settings → Delivery | NCM API token; Pathao client ID/secret + store ID (Pro+) |
| Broadcasts | Broadcast | WhatsApp approved templates (needs the WABA ID on the channel) (Pro+) |
| Viber / Website chat | Channels | commercial Viber bot token; nothing for the website widget |
| Comment → DM, comments in inbox | AI → Automations | Page `feed` / Instagram `comments` webhook fields, `pages_manage_engagement` |
| CSAT + reply-time target | Settings → Service quality | nothing (Pro+) |
| 2FA, password reset, email confirmation | Settings → Security | set `EMAIL_HOST` etc. for real emails (in DEBUG, links are printed/returned) |
| Push notifications / install as app | Settings → Notifications | HTTPS in production; `PUSH_CONTACT_EMAIL` |
| Activity log, white-label | Settings | Business plan |
| REST API keys + signed webhooks | Settings → API & webhooks | Business plan |

**Chat bubble on OmniInbox's own website:** `python manage.py setup_site_chat --email you@yourcompany.com`
creates a workspace "OmniInbox Website" (owned by you) with a website-chat channel, an AI assistant ("Omni")
that knows OmniInbox's features and current prices (read from `billing/plans.py`; re-run after a price change),
and shows the bubble on the home, pricing, docs and contact pages. Visitor chats land in that workspace's inbox.
OpenRouter spend is capped by: 500-character messages, 10 AI replies per visitor per day, 300 AI replies per day
in total, 8 messages/minute per visitor, 30 new chats/hour per IP, a shorter prompt (8 messages of history, 350
output tokens), off-topic requests declined, and the workspace's 10,000 monthly credits. Change the limits with
Channels → OmniInbox website → Edit (or `--max-chars/--ai-per-visitor/--ai-per-day`); hide it with `--disable`.
Put nginx/Cloudflare in front in production and set `TRUSTED_PROXIES` so per-IP limits see real visitor IPs.

**Showcase data:** `python manage.py seed_showcase` creates a fully populated demo shop
(login `demo@sitakurta.com` / `Kathmandu-Blue-42`) that was used for the help-center screenshots.

The worker (`python manage.py run_worker`) also polls post comments, sends "customers waiting" emails, syncs courier
tracking and resumes interrupted broadcasts, so keep it running in production.

## Operator guide: admin dashboard, Connect with Facebook, files, instant updates, Nepali

**Platform admin dashboard** (`/admin-panel`, "Admin" in the sidebar): every workspace, who's paying, MRR and revenue
(NPR/USD), trials ending, expired plans; open a workspace to see its team and payments, extend/change its plan by hand
(e.g. bank-transfer payments) or **suspend** it (its team sees a "suspended" screen with your reason; its channels,
website chat, AI bot and payment links stop; nothing is deleted). Give yourself access once:
`python manage.py make_platform_admin you@example.com` (turn on two-factor login for that account).

**Renewal reminders:** the worker emails workspace owners 7, 3 and 1 day before a plan/trial ends and once after it
ended (needs `EMAIL_HOST`). Run by hand: `python manage.py send_renewal_reminders`.

**Connect with Facebook** (one click for WhatsApp, Messenger, Instagram). One-time setup by you:
1. developers.facebook.com → create a **Business** app owned by your Business portfolio; complete **Business
   Verification** and become a **Tech Provider** (WhatsApp → Overview → "Become a Tech Provider").
2. Add products **WhatsApp**, **Messenger**, **Instagram**, **Facebook Login for Business**.
3. Facebook Login for Business → Configurations → create two:
   - *WhatsApp Embedded Signup* (login variation "WhatsApp Embedded Signup"), permissions
     `whatsapp_business_management`, `whatsapp_business_messaging`, `business_management` → copy its ID to `META_WA_CONFIG_ID`.
   - *Pages & Instagram*, permissions `pages_show_list`, `pages_messaging`, `pages_manage_metadata`,
     `pages_read_engagement`, `pages_manage_engagement`, `instagram_basic`, `instagram_manage_messages`,
     `instagram_manage_comments`, `business_management` → `META_PAGES_CONFIG_ID`.
4. Allowed domains for the JavaScript SDK + Valid OAuth redirect URIs: your app's https domain.
5. Webhooks (WhatsApp, Page, Instagram): callback `https://<your-domain>/api/webhooks/meta/`, verify token =
   `META_VERIFY_TOKEN`; subscribe `messages` (+ `message_echoes`, `messaging_postbacks`, `feed`, `comments`).
6. Put `META_APP_ID`, `META_APP_SECRET`, `META_VERIFY_TOKEN`, the two config IDs in `backend/.env`, restart.
7. Submit **App Review** for the permissions above (Advanced Access) so customers outside your business can use it.
   Until then it works for people with a role on the app. The manual token forms keep working as before.

**Photos, files, voice notes:** stored privately under `MEDIA_ROOT/attachments/` and served via signed links
(back this folder up). Max size `ATTACHMENT_MAX_MB` (25). Voice notes recorded in the browser are converted to
WhatsApp/Telegram voice format with ffmpeg (`pip install imageio-ffmpeg`, already in requirements). Instagram and
Viber fetch media from `PUBLIC_BASE_URL`, so that must be a public https address.

**Instant updates:** the browser keeps one request open to `/api/events/` and refreshes the moment anything changes.
In production run gunicorn with threads (`--worker-class gthread --threads 50`, as in the Dockerfile) and set
`REDIS_URL` so all processes share one cache (docker-compose includes Redis).

**Nepali:** users switch language from the menu under their initials or Settings → Language (saved per user).
Translations: `frontend/src/locales/ne/*.ts` (English text → Nepali). A missing translation shows English.

## Plans, billing and roles

The catalog lives in `backend/billing/plans.py`. It's the single source for the pricing page, the Billing page
and every limit check. Edit prices, limits or features there.

| Plan | NPR / month | USD / month | Channels | Seats | Adds |
|---|---|---|---|---|---|
| Free | 0 | 0 | 2 | 1 | 30-day history |
| Starter | 1,499 | 12 | 4 | 2 | Tags, saved replies |
| Pro (trial plan) | 3,999 | 29 | 10 | 6 | + internal notes, analytics, Supervisor role |
| Business | 8,999 | 69 | 25 | 15 | + agent visibility controls, CSV export, API access, priority support |
| Enterprise | Custom | Custom | Unlimited | Unlimited | Contact sales form |

- **Discounts and extras:** yearly billing is 20% off. Extra seats cost Rs. 499 / $5 per month each.
- **Trials:** new workspaces get a 14-day Pro trial.
- **Expiry:** when a plan or trial ends, the workspace falls back to Free limits. No data is deleted.
- **Payments:**
  - Khalti and eSewa charge in NPR; Stripe Checkout charges cards in USD.
  - Plans are prepaid for a month or a year. Renewing the same plan adds time to the current period.
  - A payment only activates after a server-to-server check with the gateway (amount and status). Callbacks alone never activate a plan.
  - eSewa callbacks are also signature-verified, and Stripe has a signed webhook as a backup.
- **Role permissions:** defined in `backend/core/permissions.py`:

| | Owner | Admin | Supervisor | Agent |
|---|---|---|---|---|
| Billing and plan | ✓ | | | |
| Channels, team, workspace settings | ✓ | ✓* | | |
| All conversations, assign anyone, analytics | ✓ | ✓ | ✓ | |
| Saved replies and tags management | ✓ | ✓ | ✓ | |
| Reply, notes, take or release conversations | ✓ | ✓ | ✓ | ✓ |

\* Admins manage supervisors and agents, but not the owner or other admins.

**Invites:** team invites are one-time links that expire after 7 days. They're emailed if SMTP is configured;
otherwise they're shown in the UI to copy.

## Security

Built in:

- **Tenant isolation:** every query is scoped to the caller's workspace, and `X-Workspace-Id` is validated.
- **Roles:** only owners/admins manage channels, team and demo data. Only owners can add admins.
- **Credentials:** channel secrets are Fernet-encrypted at rest, masked in API responses, and write-only.
  Only declared fields can be set, so a client can't inject OAuth tokens.
- **Auth:** JWTs with refresh-token rotation and a blacklist. A refresh token works once, and logout revokes it.
  Login and registration are rate-limited (`THROTTLE_AUTH`), and login takes the same time whether or not
  the email exists. Django's full password validators are on.
- **Webhooks:**
  - Meta: HMAC-SHA256 signature check using the app secret.
  - Telegram: secret-token header.
  - TikTok: signature required plus a 5-minute replay window.
  - Unsigned or forged requests get 403. Duplicate deliveries are ignored.
- **SSRF guard:** IMAP/SMTP hosts that resolve to private, loopback or link-local addresses (including
  cloud metadata at 169.254.169.254) are refused. `ALLOW_PRIVATE_HOSTS=true` turns this off for self-hosting.
- **Meta API calls:** the token goes in the `Authorization` header (never in URLs), plus an `appsecret_proof`.
  Turn on *Require App Secret* in your Meta app to enforce the proof.
- **Headers:**
  - Next.js: CSP, `X-Frame-Options: DENY`, nosniff, Referrer-Policy, Permissions-Policy, and HSTS in production.
  - Django: HTTPS redirect, secure cookies and HSTS when `DJANGO_DEBUG=false`.
- **Safe defaults:** DEBUG is off unless you turn it on. Production refuses to start without a real
  `DJANGO_SECRET_KEY` and `FIELD_ENCRYPTION_KEY`, and `ALLOWED_HOSTS` is an explicit list.
  `ADMIN_URL` moves the admin site off `/admin/`.

Before going to production:

1. Set these in `.env`:
   - `DJANGO_DEBUG=false`
   - a new `DJANGO_SECRET_KEY`
   - a `FIELD_ENCRYPTION_KEY`
   - `ADMIN_URL`
   - real hostnames
2. Changing to a new secret key or encryption key makes already-stored channel credentials unreadable.
   Set the keys before connecting channels, or reconnect the channels afterwards.
3. Run `python manage.py check --deploy`.
4. Consider moving JWTs from `localStorage` to httpOnly cookies. The CSP already limits XSS.

## Tests

```bash
cd backend && python manage.py test
```

95 tests cover auth (incl. 2FA, password reset, email confirmation), tenant isolation, plan limits, credential
encryption, channel webhooks with signature checks (WhatsApp, Telegram, Viber, website chat), comments, AI and
automations, orders/payments/couriers, broadcasts and opt-outs, API keys and outgoing webhooks.

## Production checklist / next milestones

- [ ] Set `DJANGO_DEBUG=false`, a strong `DJANGO_SECRET_KEY`, and a `FIELD_ENCRYPTION_KEY`
- [ ] HTTPS everywhere; restrict `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`
- [ ] Move `send_reply` and webhook processing onto a queue (Celery/RQ + Redis) for retries
- [ ] Real-time updates over WebSockets (Django Channels) instead of 5-second polling
- [ ] Attachments: download media and send images/files
- [ ] Gmail API OAuth
- [ ] Meta App Review, TikTok Business Messaging approval

## Affiliate program (recurring commissions)

Anyone with an OmniInbox login can apply to become an affiliate (account menu → **Refer & earn**, or `/affiliate`).
You approve them in **Admin → Affiliates**. Approved affiliates get:

- a **tracking link** `https://<your-domain>/r/CODE` (also `?ref=CODE` on any page). The visitor is remembered for 60 days
  and the code is filled in on the sign-up form automatically;
- a **promo code** customers can type when signing up, or on the **Billing** page before their first payment.

**Commission:** 20% of every subscription payment from a referred workspace, on every renewal, for as long as it stays
subscribed (lifetime, recurring). Each commission is held 14 days (refund window), then becomes available. Affiliates
request a payout once they have Rs 2,000 (or $15) available; you send it by eSewa / Khalti / bank, then enter the
transaction ID in Admin → Affiliates → **Mark paid** (the affiliate is emailed). Rejecting a payout returns the money to
their balance. You can set a custom rate per affiliate, suspend them (they stop earning), and void a commission
(e.g. after a refund) in the Django admin.

Rules: one referrer per workspace, forever; no self-referral; a promo code can't be added after the first payment;
affiliates only see masked customer names. Payout account details are encrypted at rest.

| Setting (`backend/.env`) | Default | |
|---|---|---|
| `AFFILIATE_COMMISSION_RATE` | `0.20` | default rate for new affiliates |
| `AFFILIATE_HOLD_DAYS` | `14` | days before a commission can be paid out |
| `AFFILIATE_MIN_PAYOUT_NPR` / `_USD` | `2000` / `15` | minimum withdrawal |

API: `affiliates/code/<code>/`, `affiliates/click/` (public) · `affiliates/me/` (GET/POST/PATCH), `affiliates/payouts/`
· `billing/promo-code/` · platform admin: `platform/affiliates/`, `platform/affiliates/<id>/`,
`platform/affiliate-payouts/`, `platform/affiliate-payouts/<id>/`.

## AI knowledge base: documents, websites and search by meaning

AI → **Knowledge base** lets each organisation teach its own AI (nothing is shared between workspaces):

- **Upload a document**: PDF (with selectable text), Word `.docx` or `.txt`, up to 10 MB / 300 pages. It is split
  into entries by heading (Fee Structure, Admission Process, Visa Checklist…). Review and edit them under the document;
  deleting the document removes its entries. Scanned-image PDFs are rejected with a clear message.
- **Import a website**: paste the address; with "also read linked pages" it reads up to 15 pages of the same site,
  preferring About / Courses / Fees / Admission / FAQ / Visa pages and skipping menus, footers, logins and files.
  Internal addresses are blocked (SSRF guard). The ↻ button re-imports to pick up changes.
- **Write an answer** by hand, as before.
- **Search by meaning**: each entry gets an embedding (OpenRouter `/embeddings`, same API key; default
  `openai/text-embedding-3-small`, about $0.02 per million tokens), so "padhna kati paisa lagcha?" finds the "Tuition"
  entry. It is combined with keyword search that knows common Nepali / Romanized Nepali words (kati, shulka, bharna,
  kagaj, भिसा…). Without embeddings, keyword search alone is used. "What would the AI find?" tests this for free.
- **Sources for staff**: every AI reply in a conversation shows **Based on: entry · document**; click it to open and
  fix the entry. Suggested drafts and the Test tab show the same.

| Setting (`backend/.env`) | Default | |
|---|---|---|
| `EMBEDDINGS_ENABLED` | `true` | `false` = keyword search only |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | any OpenRouter embedding model |

Limits per workspace: 30 documents/websites (300 entries each) plus 300 hand-written entries. Run
`pip install -r requirements.txt` (adds `pypdf`) and `python manage.py migrate` after updating.

## AI sales staff (AI → Sales staff)

Turn the chatbot into a salesperson. Everything is off by default and switched on per workspace.

* **Takes orders in chat.** The AI recommends products from Products (with their real prices, options and stock),
  collects name, 10-digit mobile, address and payment method, then sends an order summary built from the database
  (never from prices the model wrote). The order is created only when the customer replies YES. It shows up in Orders
  with an **AI** badge, already *Confirmed*; online orders get a Khalti/eSewa link, bank orders get your bank details.
* **Books visits & appointments** (counselling sessions, campus visits, trial classes...) inside your business hours,
  with a capacity per time slot. If the time is taken or closed, the AI offers the next free times. See them on **Visits**;
  customers get a reminder 1–3 hours before when the channel allows it.
* **Follows up** once with customers who were interested and went quiet (after N hours, default 3). Cancelled if anyone
  writes first. Messenger / Instagram / WhatsApp only allow business messages within 24 hours of the customer's last
  message, so there follow-ups go out within 22 hours or are skipped.
* **Understands voice notes.** Incoming voice messages are transcribed (Nepali in Devanagari, English, mixed); the
  transcript shows under the audio player and the AI answers it like a text. 1 credit per voice note.
* **Checks payment screenshots.** eSewa / Khalti / Fonepay / bank screenshots are read (amount, transaction ID, date,
  receiver, status, visible edits) and matched to the customer's unpaid order. Each one is marked *Looks valid*,
  *Needs a look* or *Suspicious* (reused transaction ID, wrong amount or receiver, failed status, old date, edits).
  **The AI never marks anything paid**: staff press *Confirm paid* above the reply box. Add how your account appears on
  screenshots in Settings → Shop so receivers can be checked.
* **Delivery on autopilot.** Settings → Shop → Delivery → *Book the courier automatically* (when paid, or when confirmed
  incl. COD) with Nepal Can Move or Pathao. Customers get "shipped", "out for delivery" and "delivered" messages.
  If an address can't be matched (e.g. a Pathao zone) the team gets a note to book it by hand.
* **"While you were away"** banner in the inbox and a 24-hour report on the Sales staff tab.

Setup: `python manage.py migrate`, set `AI_AUDIO_MODEL` / `AI_VISION_MODEL` if you don't want Gemini Flash, and keep
`python manage.py run_worker` running (follow-ups, visit reminders and delivery tracking run there).
API: `GET /api/ai/report/?hours=24`, `GET /api/payment-checks/?conversation=&status=pending`,
`POST /api/payment-checks/<id>/confirm|reject/`, `GET|POST /api/bookings/`, `PATCH|DELETE /api/bookings/<id>/`.

## Smart publisher (Publish page)

Upload a video once, let AI write for every platform, check one simple card per platform, press **Publish to all**.

* **Fill everything with AI** watches the video (a few frames) and listens to it (speech in Nepali or English), then
  writes a YouTube title, description, tags and category, an Instagram caption with hashtags, a TikTok caption and the
  Facebook text, using your knowledge base for prices and details. It also lists checks such as a price in the video
  that doesn't match your catalogue. 2 credits for a video with sound, 1 otherwise. Needs ffmpeg (bundled through
  `imageio-ffmpeg`) and `AI_VISION_MODEL` / `AI_AUDIO_MODEL` (Gemini Flash by default).
* **Per-platform settings**, with only the essentials shown and the rest under "More options" (remembered per account):
  YouTube title, privacy, tags, category, made for kids, notify subscribers · TikTok who can see it (from the creator's
  allowed options, no default, as TikTok requires), comments / duet / stitch, commercial content disclosure ·
  Instagram Reel in grid, collaborators, first comment · Facebook video title, first comment.
* **Checks before posting**: video length per platform (read with ffmpeg on upload), YouTube title rules and tag length,
  TikTok privacy and branded-content rules, Instagram Reels 3 s–15 min; hints for horizontal videos and YouTube Shorts.
* **Publish to all** uploads to every platform at the same time and shows live progress with a link to each live post,
  plus "Retry failed".

Run `python manage.py migrate` (adds video size/length). TikTok posts stay "Only me" until TikTok audits your app; the
TikTok card already shows the notices TikTok's audit asks for.
