export type User = { id: number; email: string; name: string };
export type MeUser = User & { email_verified: boolean; two_factor_enabled: boolean; push_devices: number; is_platform_admin: boolean; language: "en" | "ne" };

export type Role = "owner" | "admin" | "supervisor" | "agent";

export type Workspace = {
  id: string;
  name: string;
  slug: string;
  plan: string;
  effective_plan: string;
  plan_name: string;
  billing_cycle: "monthly" | "yearly";
  plan_expires_at: string | null;
  trial_ends_at: string | null;
  is_trialing: boolean;
  is_expired: boolean;
  extra_seats: number;
  currency: "NPR" | "USD";
  channel_limit: number;
  seat_limit: number;
  features: string[];
  agents_see_all: boolean;
  unanswered_alert_minutes: number;
  sla_minutes: number;
  csat_enabled: boolean;
  csat_question: string;
  brand: Brand;
  suspended: { at: string; reason: string } | null;
};
export type Brand = { name: string; color: string; logo_url: string; hide_powered_by: boolean };

export type Capability =
  | "manage_billing" | "manage_channels" | "manage_team" | "manage_settings" | "manage_canned"
  | "manage_tags" | "view_analytics" | "see_all_conversations" | "assign_others" | "publish_posts"
  | "manage_social_accounts" | "manage_automations" | "view_audit_log" | "manage_products" | "manage_shop" | "send_broadcasts" | "manage_developers";

export type Me = {
  user: MeUser;
  workspace: Workspace;
  role: Role;
  capabilities: Capability[];
  memberships: Array<{ role: Role; workspace: Workspace }>;
};

export type Tag = { id: number; name: string; color: string };
export type CannedReply = { id: number; shortcut: string; title: string; body: string };

export type PlanPrice = { monthly: number; yearly: number; yearly_per_month: number };
export type Plan = {
  key: string;
  name: string;
  tagline: string;
  prices: { NPR: PlanPrice; USD: PlanPrice } | null;
  channels: number;
  seats: number;
  history_days: number | null;
  ai_credits: number;
  features: string[];
  popular: boolean;
};
export type Catalog = {
  plans: Plan[];
  feature_labels: Record<string, string>;
  extra_seat: { NPR: number; USD: number };
  yearly_discount: number;
  trial_days: number;
  trial_plan: string;
};

export type Payment = {
  id: string; plan: string; cycle: string; currency: string; amount: string; gateway: string;
  status: "pending" | "paid" | "failed"; created_at: string; paid_at: string | null; period_end: string | null;
  failure_reason: string;
};

export type Billing = {
  plan: string; effective_plan: string; plan_name: string; billing_cycle: string; plan_expires_at: string | null;
  trial_ends_at: string | null; is_trialing: boolean; is_expired: boolean; extra_seats: number;
  limits: { channels: number; seats: number }; usage: { channels: number; seats: number }; features: string[];
  gateways: Array<{ key: "khalti" | "esewa" | "stripe"; currency: "NPR" | "USD" }>;
  payments: Payment[]; can_manage: boolean;
  promo_code: string | null; can_add_promo_code: boolean;
};

/* ---------------- affiliate program (Money is defined with the platform-admin types) ---------------- */
export type AffiliateStatus = "pending" | "approved" | "rejected" | "suspended";
export type PayoutMethod = "esewa" | "khalti" | "bank";
export type PayoutDetails = { account_name: string; account_number: string; bank_name?: string };
export type AffiliateProgram = { rate: string; hold_days: number; min_payout: Money; link_base: string };
export type AffiliateAccount = {
  id: number; code: string; link: string; status: AffiliateStatus; rate: string; admin_note: string;
  created_at: string; approved_at: string | null;
  payout_method?: PayoutMethod | ""; payout_details?: PayoutDetails | Record<string, never>; pitch?: string;
};
export type AffiliateBalances = { holding: Money; available: Money; requested: Money; paid: Money; lifetime: Money };
export type AffiliateStats = { clicks: number; unique_visitors: number; clicks_30d: number; signups: number; paying: number };
export type CommissionState = "holding" | "available" | "requested" | "paid" | "void";
export type AffiliateCommission = {
  id: number; workspace: string; plan: string; cycle: string; base_amount: string; rate: string; amount: string;
  currency: "NPR" | "USD"; state: CommissionState; available_at: string; created_at: string;
};
export type AffiliatePayout = {
  id: number; amount: string; currency: "NPR" | "USD"; status: "requested" | "paid" | "rejected"; method: string;
  reference: string; note: string; requested_at: string; processed_at: string | null;
  details?: PayoutDetails; affiliate?: { id: number; code: string; email: string; name: string };
};
export type ReferredWorkspaceStatus = "trial" | "subscribed" | "cancelled" | "free";
export type AffiliateDashboard = {
  program: AffiliateProgram; suggested_code: string; affiliate: AffiliateAccount | null;
  stats?: AffiliateStats; balances?: AffiliateBalances; commissions?: AffiliateCommission[]; payouts?: AffiliatePayout[];
  referrals?: Array<{ workspace: string; source: "link" | "code"; joined_at: string; status: ReferredWorkspaceStatus }>;
};
export type AdminAffiliateRow = AffiliateAccount & {
  email: string; name: string; signups: number; paying: number; lifetime: Money; owed: Money;
};
export type AdminAffiliateList = {
  summary: { pending_applications: number; active: number; payouts_requested: number; owed: Money; paid_all_time: Money; referred_revenue: Money };
  results: AdminAffiliateRow[];
};
export type AdminAffiliateDetail = AffiliateAccount & {
  email: string; name: string; stats: AffiliateStats; balances: AffiliateBalances;
  referrals: Array<{ workspace: { id: string; name: string }; source: "link" | "code"; joined_at: string; status: ReferredWorkspaceStatus }>;
  commissions: AffiliateCommission[]; payouts: AffiliatePayout[];
};

export type Member = { id: number; email: string; name: string; role: Role; joined_at: string };
export type Invite = { id: string; email: string; role: Role; expires_at: string; url: string; invited_by: string | null };
export type Team = { members: Member[]; invites: Invite[]; seats_used: number; seat_limit: number };

export type Analytics = {
  days: number;
  totals: { new_conversations: number; incoming: number; outgoing: number; closed: number; avg_first_response_minutes: number | null };
  series: Array<{ date: string; in: number; out: number }>;
  by_channel: Array<{ provider: string; incoming: number; outgoing: number }>;
  by_agent: Array<{ name: string; replies: number }>;
  sla?: AnalyticsQuality["sla"];
  csat?: AnalyticsQuality["csat"];
};

export type ProviderField = {
  name: string;
  label: string;
  type: "text" | "password" | "number" | "select";
  required: boolean;
  secret: boolean;
  help: string;
  default: string;
  options: string[];
};

export type ProviderMeta = {
  key: string;
  label: string;
  category: "chat" | "social" | "email";
  color: string;
  fields: ProviderField[];
  receive_mode: string;
  setup_steps: string[];
  uses_oauth: boolean;
  beta: boolean;
};

export type Channel = {
  id: string;
  provider: string;
  name: string;
  credentials_preview: Record<string, string>;
  status: "pending" | "active" | "error" | "disabled";
  last_error: string;
  last_synced_at: string | null;
  is_demo: boolean;
  webhook_url: string;
  verify_token: string | null;
  receive_mode: string;
  unread_count: number | null;
  authorized: boolean;
  webhook_public: boolean;
  created_at: string;
};

export type Contact = { id: string; name: string; handle: string; avatar_url: string; external_id: string; notes: string };

export type Conversation = {
  id: string;
  channel: { id: string; provider: string; name: string; is_demo: boolean; can_send_media?: boolean };
  contact: Contact;
  subject: string;
  status: "open" | "pending" | "closed";
  assigned_to: User | null;
  tags: Tag[];
  unread_count: number;
  last_message_at: string | null;
  last_message_preview: string;
  ai?: ConversationAI;
  kind?: "message" | "comment";
  last_direction?: "in" | "out" | null;
};

export type AICategory = "order" | "question" | "lead" | "complaint" | "support" | "feedback" | "spam" | "other";
export type Sentiment = "positive" | "neutral" | "negative";
export type AISummary = { summary: string; category: AICategory; sentiment: Sentiment; next_step: string; at: string };
export type ConversationAI = {
  bot_paused: boolean; pause_reason: string; handoff_reason: string;
  category: AICategory | ""; sentiment: Sentiment | ""; summary: AISummary | null;
};

export type Message = {
  id: string;
  direction: "in" | "out";
  is_note: boolean;
  bot: "" | "ai" | "rule";
  sender_name: string;
  text: string;
  html: string;
  attachments: Attachment[];
  status: "pending" | "sent" | "received" | "failed";
  error: string;
  sent_at: string;
  created_at: string;
  sources?: KnowledgeRef[];
};

export type Stats = {
  total_conversations: number;
  open: number;
  unread_conversations: number;
  unread_messages: number;
  assigned_to_me: number;
  unread_by_kind?: { message: number; comment: number };
  ai_handoff?: number;
  by_provider: Record<string, { conversations: number; unread: number }>;
};

export type PublishPlatform = "facebook" | "instagram" | "youtube" | "tiktok";
export type SocialAccount = {
  id: string; platform: PublishPlatform; name: string; avatar_url: string; status: "active" | "error"; last_error: string;
};
export type MediaAsset = {
  id: string; kind: "image" | "video"; mime: string; size: number; name: string; preview_url: string;
  width?: number | null; height?: number | null; duration?: number | null;
};
/** Per-platform publishing settings (YouTube title/tags, TikTok privacy/toggles, Instagram collaborators...). */
export type PublishOptions = {
  title?: string; privacy?: string; tags?: string[]; category_id?: string; made_for_kids?: boolean; notify_subscribers?: boolean;
  disable_comment?: boolean; disable_duet?: boolean; disable_stitch?: boolean; brand_organic?: boolean; brand_content?: boolean;
  share_to_feed?: boolean; collaborators?: string[]; first_comment?: string; cover_ms?: number; note?: string;
};
export type TikTokCreator = {
  nickname: string; username: string; avatar_url: string; privacy_options: string[];
  comment_disabled: boolean; duet_disabled: boolean; stitch_disabled: boolean; max_seconds: number;
};
export type PublishFill = {
  summary: string; transcript: string; checks: string[]; credits_used: number;
  youtube?: { title: string; description: string; tags: string[]; category_id: string };
  instagram?: { caption: string }; tiktok?: { caption: string }; facebook?: { caption: string; title: string };
};
export type PostTarget = {
  account: SocialAccount; caption: string; options: PublishOptions;
  status: "pending" | "publishing" | "published" | "failed"; url: string; error: string; published_at: string | null;
};
export type SocialPost = {
  id: string; caption: string; status: "draft" | "scheduled" | "publishing" | "published" | "partial" | "failed";
  scheduled_at: string | null; published_at: string | null; created_at: string; media: MediaAsset | null;
  created_by: string; targets: PostTarget[];
};
export type PublishConfig = {
  platforms: Record<PublishPlatform, { label: string; connect: "token" | "via_facebook" | "oauth"; enabled: boolean }>;
  limits: Record<PublishPlatform, { caption: number; title?: number; needs_media: boolean; video_only: boolean; jpeg_only: boolean }>;
  youtube_categories?: Record<string, string>;
  features: { publish: boolean; schedule: boolean };
  account_limit: number;
  /** One-click "Continue with Facebook" (null when the server has no Facebook Login configuration). */
  facebook_login: { app_id: string; graph_version: string; config_id: string } | null;
};

// ---------------------------------------------------------------- AI & automations
export type DayHours = { on: boolean; start: string; end: string };
export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type BotMode = "off" | "after_hours" | "always";
export type AICredits = { limit: number; used: number; remaining: number; tokens: number };
export type AISettings = {
  business_name: string; about: string; tone: "friendly" | "professional" | "casual"; bot_name: string;
  bot_mode: BotMode; handoff_message: string; auto_tag: boolean; timezone: string; hours: Record<Weekday, DayHours>;
  is_open: boolean; configured: boolean; model: string;
  sales_orders: boolean; sales_bookings: boolean; booking_label: string; booking_minutes: number; booking_capacity: number;
  followup_enabled: boolean; followup_hours: number; voice_notes: boolean; check_payments: boolean;
  features: { ai: boolean; automations: boolean; bot: boolean; orders: boolean };
  credits: AICredits; knowledge_count: number;
};
export type KnowledgeItem = {
  id: number; title: string; content: string; updated_at: string;
  source: { id: number; name: string; kind: "file" | "website" } | null;
};
export type KnowledgeSource = {
  id: number; kind: "file" | "website"; name: string; url: string; crawl: boolean;
  status: "processing" | "ready" | "failed"; error: string; pages: number; chars: number; entries: number;
  created_at: string; updated_at: string;
};
/** A knowledge entry an AI answer was based on (shown to the team). */
export type KnowledgeRef = { id: number; kind: "knowledge" | "saved_reply"; title: string; source: string };
export type KnowledgeMatch = KnowledgeRef & { content: string; source_kind: string; score: number; match: "meaning" | "keywords" };
export type RuleTrigger = "keyword" | "welcome" | "away" | "comment";
export type AutomationRule = {
  id: string; name: string; enabled: boolean; trigger: RuleTrigger;
  channel: { id: string; provider: string; name: string } | null;
  keywords: string[]; match: "contains" | "exact"; post_id: string; reply_text: string; use_ai: boolean;
  public_reply_text: string; add_tag_id: number | null; assign_to_id: number | null;
  run_count: number; last_run_at: string | null; last_error: string; created_at: string;
};
export type RuleInput = Partial<Omit<AutomationRule, "id" | "channel" | "run_count" | "last_run_at" | "last_error" | "created_at">> & {
  channel_id?: string | null;
};
export type BotAnswer = { reply: string; handoff: boolean; reason: string; category: AICategory; sentiment: Sentiment; sources?: KnowledgeRef[] };
export type RewriteMode = "improve" | "shorter" | "friendlier" | "professional" | "nepali" | "romanized" | "english";

// ---------------------------------------------------------------- accounts, security, notifications
export type LoginResult = { access: string; refresh: string } | { two_factor_required: true; ticket: string };
export type OnboardingStep = { key: string; title: string; help: string; done: boolean; href: string | null };
export type Onboarding = { steps: OnboardingStep[]; done: number; total: number; dismissed: boolean };
export type AuditRow = { id: number; action: string; label: string; actor: string; target: string; meta: Record<string, unknown>; ip: string | null; created_at: string };
export type NotificationPrefs = { email_unanswered: boolean; push_devices: number; unanswered_alert_minutes: number };

// ---------------------------------------------------------------- commerce
export type OrderStatus = "new" | "confirmed" | "packed" | "shipped" | "delivered" | "cancelled" | "returned";
export type PaymentMethod = "cod" | "khalti" | "esewa" | "bank" | "cash";
export type PaymentStatus = "unpaid" | "pending" | "paid" | "refunded";
export type Product = {
  id: number; name: string; sku: string; description: string; price: string; compare_at_price: string | null;
  stock: number | null; variants: string[]; image_id: string | null; image_url: string; weight_kg: string; active: boolean;
};
export type CustomerContact = { id: string; name: string; handle: string; provider: string; channel: string; conversation_id: string };
export type Customer = {
  id: string; name: string; phone: string; email: string; address: string; city: string; district: string; notes: string;
  created_at: string; orders_count?: number; total_spent?: string; last_order_at?: string | null;
  contacts?: CustomerContact[]; providers?: string[]; orders?: OrderSummary[];
};
export type OrderItem = { id?: number; product_id: number | null; name: string; variant: string; quantity: number; unit_price: string; line_total?: string; image_url?: string };
export type OrderSummary = {
  id: string; number: string; status: OrderStatus; status_label: string; payment_method: PaymentMethod; payment_status: PaymentStatus;
  currency: string; subtotal: string; delivery_charge: string; discount: string; total: string;
  recipient_name: string; recipient_phone: string; address: string; city: string; district: string; note: string;
  courier: string; courier_name: string; tracking_id: string; tracking_url: string; delivery_status: string;
  created_at: string; paid_at: string | null; shipped_at: string | null; delivered_at: string | null;
  conversation_id: string | null; customer: { id: string; name: string } | null; items_count: number; provider: string | null;
  source: "manual" | "ai" | "api";
};
export type Order = OrderSummary & {
  items: OrderItem[]; history: Array<{ at: string; text: string; by: string }>; created_by: string;
  payment_links: Array<{ id: string; url: string; amount: string; status: string; gateway: string; created_at: string }>;
};
export type OrderStats = { by_status: Partial<Record<OrderStatus, number>>; month_orders: number; month_revenue: string; month_collected: string; unpaid: number };
export type ShopSettings = {
  currency: string; order_prefix: string; delivery_inside_valley: string; delivery_outside_valley: string; bank_details: string;
  khalti_live: boolean; esewa_live: boolean; esewa_merchant_code: string; ncm_live: boolean; ncm_from_branch: string;
  pathao_base_url: string; pathao_store_id: string; msg_order_summary: string; msg_paid: string; msg_shipped: string; msg_delivered: string;
  auto_message_paid: boolean; auto_message_shipped: boolean; auto_message_delivered: boolean;
  msg_out_for_delivery: string; auto_message_out_for_delivery: boolean;
  auto_ship: "off" | "paid" | "confirmed"; default_courier: "" | "ncm" | "pathao"; payment_receivers: string;
  configured: { khalti: boolean; esewa: boolean; ncm: boolean; pathao: boolean };
  gateways: string[]; couriers: string[]; features: { orders: boolean; couriers: boolean };
};
export type ShopSettingsInput = Partial<Omit<ShopSettings, "configured" | "gateways" | "couriers" | "features">> & {
  khalti_secret_key?: string; esewa_secret_key?: string; ncm_token?: string;
  pathao?: { client_id?: string; client_secret?: string; username?: string; password?: string };
};
export type OrderInput = {
  conversation_id?: string | null; customer_id?: string | null; items?: Array<{ product_id?: number | null; name?: string; variant?: string; quantity: number; unit_price?: string | null }>;
  payment_method?: PaymentMethod; delivery_charge?: string; discount?: string; recipient_name?: string; recipient_phone?: string;
  address?: string; city?: string; district?: string; note?: string;
};
export type PublicPayment = {
  shop: string; order: string; amount: string; currency: string; status: string; delivery_charge: string; discount: string;
  items: Array<{ name: string; variant: string; quantity: number; line_total: string }>; gateways: string[];
  test_mode: { khalti: boolean; esewa: boolean };
  brand: Brand;
};

// ---------------------------------------------------------------- broadcasts
export type BroadcastAudience = { tags?: number[]; active_days?: number | null; customers_only?: boolean };
export type Broadcast = {
  id: string; name: string; channel: { id: string; provider: string; name: string }; kind: "text" | "template"; text: string;
  template_name: string; template_language: string; template_body: string; variables: string[]; audience: BroadcastAudience;
  status: "draft" | "sending" | "done" | "cancelled"; total: number; sent: number; failed: number;
  created_at: string; started_at: string | null; finished_at: string | null; created_by: string;
  errors?: Array<{ conversation__contact__name: string; error: string }>;
};
export type WhatsAppTemplate = { name: string; language: string; status: string; category: string; body: string; variables: number; media_header: boolean };

// ---------------------------------------------------------------- developers / quality
export type ApiKeyRow = { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null; created_by: string; key?: string };
export type WebhookEndpoint = { id: string; url: string; events: string[]; active: boolean; failures: number; last_status: number | null;
  last_error: string; last_delivery_at: string | null; created_at: string; secret: string };
export type WebhookDeliveryRow = { id: number; event: string; status: number | null; error: string; attempts: number; duration_ms: number; created_at: string };
export type AnalyticsQuality = {
  sla: { target_minutes: number; met_pct: number | null; measured: number };
  csat: { enabled: boolean; responses: number; avg: number | null; happy_pct: number | null;
    by_agent: Array<{ name: string; avg: number; responses: number }>; recent: Array<{ score: number; comment: string; at: string; contact: string }> };
};

export type Attachment = {
  id: string;
  kind: "image" | "video" | "audio" | "voice" | "file" | "sticker";
  name: string;
  mime: string;
  size: number;
  status: "pending" | "ready" | "failed" | "unavailable";
  error: string;
  url: string;
  /** What a voice note says (AI transcription) */
  transcript?: string;
  /** What the AI saw in a photo */
  ai?: { is_payment: boolean; description: string } | null;
};

// ---------------------------------------------------------------- AI sales staff
export type PaymentCheck = {
  id: number; app: string; app_label: string; amount: string | null; txn_id: string; paid_on: string; receiver: string; sender: string;
  verdict: "valid" | "check" | "suspicious" | "not_payment"; verdict_label: string; reasons: string[];
  status: "pending" | "confirmed" | "rejected"; created_at: string; reviewed_by: string;
  order: { id: string; number: string; total: string; payment_status: PaymentStatus } | null;
  image: Attachment | null; conversation_id: string | null;
};
export type BookingStatus = "booked" | "confirmed" | "done" | "no_show" | "cancelled";
export type Booking = {
  id: string; name: string; phone: string; purpose: string; starts_at: string; minutes: number; status: BookingStatus;
  status_label: string; note: string; source: "manual" | "ai"; created_at: string; conversation_id: string | null;
  provider: string | null; customer_id: string | null;
};
export type BookingInput = Partial<Pick<Booking, "name" | "phone" | "purpose" | "starts_at" | "minutes" | "status" | "note">> & { notify?: boolean };
export type AIReport = {
  since: string; conversations_answered: number; replies: number; orders: number; orders_total: string; visits: number;
  voice_notes: number; payment_checks: number; payments_to_confirm: number; followups: number; handoffs: number; upcoming_visits: number;
};

export type Money = { NPR: string; USD: string };
export type PlatformInsights = {
  users: {
    total: number; verified: number; two_factor: number;
    signups: { today: number; d7: number; d30: number }; active: { d1: number; d7: number; d30: number };
    signups_by_day: Array<{ day: string; count: number }>;
    recent: Array<{ name: string; email: string; joined: string; last_login: string | null; workspace: string }>;
  };
  ai: {
    month: string; model: string; configured: boolean; credits: number; tokens: number; cost_usd: string; cost_per_million_usd: string;
    workspaces_using: number; near_limit: number; bot_replies: { d1: number; d30: number }; handoffs_30d: number;
    by_month: Array<{ month: string; credits: number; tokens: number; cost_usd: string }>;
    top: Array<{ id: string; name: string; plan: string; credits: number; limit: number; tokens: number; cost_usd: string }>;
  };
  affiliates: {
    total: number; pending: number; approved: number; suspended: number; clicks_30d: number; referrals: number;
    referrals_30d: number; paying_referrals: number; payouts_requested: number; owed: Money; paid: Money;
    top: Array<{ id: number; code: string; name: string; signups: number; earned: Money }>;
  };
  activity: {
    messages_30d: { in: number; out: number }; conversations_30d: number; channels: Array<{ provider: string; count: number }>;
    orders_30d: { count: number; value: Record<string, string> }; posts_published_30d: number; broadcast_messages_30d: number;
  };
  funnel: { created_90d: number; paid_90d: number; conversion: number };
};

export type PlatformOverview = {
  workspaces: { total: number; paying: number; trial: number; expired: number; free: number; suspended: number; internal: number };
  trials_ending_7d: number;
  users: number;
  plans: Array<{ plan: string; name: string; count: number }>;
  mrr: Money;
  revenue: { this_month: Money; last_month: Money; last_30_days: Money; all_time: Money };
  revenue_by_month: Array<{ month: string } & Money>;
  signups_by_day: Array<{ day: string; count: number }>;
  recent_payments: PlatformPayment[];
};
export type PlatformPayment = {
  id: string; workspace: { id: string; name: string }; plan: string; cycle: string; currency: string; amount: string;
  gateway: string; status: string; paid_at: string | null; created_at: string;
};
export type PlatformWorkspace = {
  id: string; name: string; slug: string; status: "paying" | "trial" | "expired" | "free" | "suspended" | "internal";
  plan: string; plan_name: string; billing_cycle: string; currency: string; plan_expires_at: string | null; trial_ends_at: string | null;
  owner: { name: string; email: string } | null; members: number; channels: number; last_activity: string | null;
  total_paid: Money; mrr: string; suspended_at: string | null; suspended_reason: string; created_at: string;
};
export type PlatformWorkspaceDetail = {
  id: string; name: string; status: PlatformWorkspace["status"]; plan: string; plan_expires_at: string | null; suspended_reason: string;
  members: Array<{ name: string; email: string; role: string; last_login: string | null }>;
  payments: PlatformPayment[];
  usage: { conversations: number; messages_30d: number };
};
export type MetaConfig = {
  app_id: string; graph_version: string;
  whatsapp: { enabled: boolean; config_id: string };
  pages: { enabled: boolean; config_id: string };
};
export type MetaPage = {
  id: string; name: string; picture: string; connected: boolean;
  instagram: { id: string; username: string; connected: boolean } | null;
};
