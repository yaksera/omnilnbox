"use client";

import type {
  Attachment, MetaConfig, MetaPage, PlatformInsights, PlatformOverview, PlatformWorkspace, PlatformWorkspaceDetail,
  Broadcast, BroadcastAudience, WhatsAppTemplate, ApiKeyRow, Brand, WebhookEndpoint, WebhookDeliveryRow,
  Customer, Order, OrderInput, OrderStats, OrderSummary, Product, PublicPayment, ShopSettings, ShopSettingsInput,
  AuditRow, LoginResult, NotificationPrefs, Onboarding,
  AISettings, AISummary, AutomationRule, BotAnswer, KnowledgeItem, RewriteMode, RuleInput,
  Analytics, Billing, MediaAsset, PublishConfig, SocialAccount, SocialPost, CannedReply, Catalog, Channel, Conversation, Invite, Me, Member, Message, ProviderMeta, Role, Stats, Tag,
  Team, User, Workspace,
  KnowledgeMatch, KnowledgeRef, KnowledgeSource, AIReport, PublishFill, PublishOptions, TikTokCreator, Booking, BookingInput, PaymentCheck,
  AdminAffiliateDetail, AdminAffiliateList, AffiliateAccount, AffiliateDashboard, AffiliatePayout, PayoutDetails, PayoutMethod,
} from "./types";

// Default: same-origin proxy (see next.config.ts). Set NEXT_PUBLIC_API_URL only if you
// deliberately want the browser to call the API directly (then configure CORS in Django).
const DIRECT_API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
export const API_BASE = DIRECT_API ? `${DIRECT_API}/api` : "/backend";

async function doFetch(url: string, init?: RequestInit) {
  try {
    return await fetch(url, init);
  } catch {
    throw new ApiError(0, "Cannot reach the API server. Make sure the Django backend is running (python manage.py runserver).");
  }
}

const ACCESS = "omni.access";
const REFRESH = "omni.refresh";
const WORKSPACE = "omni.workspace";

function read(key: string) {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

export const auth = {
  get access() {
    return read(ACCESS);
  },
  get refresh() {
    return read(REFRESH);
  },
  set(tokens: { access: string; refresh?: string }) {
    write(ACCESS, tokens.access);
    if (tokens.refresh) write(REFRESH, tokens.refresh);
  },
  clear() {
    write(ACCESS, null);
    write(REFRESH, null);
    write(WORKSPACE, null);
  },
  get workspace() {
    return read(WORKSPACE);
  },
  setWorkspace(id: string) {
    write(WORKSPACE, id);
  },
  isLoggedIn() {
    return !!read(ACCESS);
  },
};

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, data: unknown) {
    super(ApiError.format(data) || `Request failed (${status})`);
    this.status = status;
    this.data = data;
  }
  static format(data: unknown): string {
    if (!data) return "";
    if (typeof data === "string") return data;
    if (typeof data === "object") {
      const d = data as Record<string, unknown>;
      if (typeof d.detail === "string") return d.detail;
      return Object.entries(d)
        .map(([k, v]) => {
          if (Array.isArray(v)) return `${k}: ${v.join(" ")}`;
          if (v && typeof v === "object") return ApiError.format(v);
          return `${k}: ${String(v)}`;
        })
        .join(" · ");
    }
    return "";
  }
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const refresh = auth.refresh;
  if (!refresh) return false;
  if (!refreshing) {
    refreshing = doFetch(`${API_BASE}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    })
      .then(async (r) => {
        if (!r.ok) return false;
        auth.set(await r.json());
        return true;
      })
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshing = null), 0);
      });
  }
  return refreshing;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(init.json);
  }
  if (auth.access) headers.set("Authorization", `Bearer ${auth.access}`);
  if (auth.workspace) headers.set("X-Workspace-Id", auth.workspace);

  const res = await doFetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401 && retry && (await tryRefresh())) {
    return api<T>(path, init, false);
  }
  if (res.status === 401) {
    auth.clear();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      // Hard redirect: this helper runs outside React components.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/login";
    }
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

type Paginated<T> = { count: number; results: T[] };

export const Api = {
  register: (body: { name: string; email: string; password: string; workspace_name?: string;
    referral_code?: string; referral_source?: "link" | "code" }) =>
    api<{ access: string; refresh: string }>("/auth/register/", { method: "POST", json: body }),
  login: (body: { email: string; password: string }) =>
    api<LoginResult>("/auth/login/", { method: "POST", json: body }),
  loginTwoFactor: (ticket: string, code: string) =>
    api<{ access: string; refresh: string }>("/auth/2fa/login/", { method: "POST", json: { ticket, code } }),
  forgotPassword: (email: string) => api<{ detail: string; dev_link?: string }>("/auth/password/forgot/", { method: "POST", json: { email } }),
  resetPassword: (body: { uid: string; token: string; password: string }) =>
    api("/auth/password/reset/", { method: "POST", json: body }),
  sendVerification: () => api<{ ok: boolean; dev_link?: string; already?: boolean }>("/auth/email/send-verification/", { method: "POST" }),
  verifyEmail: (token: string) => api<{ email: string }>("/auth/email/verify/", { method: "POST", json: { token } }),
  twoFactorSetup: () => api<{ secret: string; uri: string; qr_svg: string }>("/auth/2fa/setup/", { method: "POST" }),
  twoFactorEnable: (code: string) => api<{ recovery_codes: string[] }>("/auth/2fa/enable/", { method: "POST", json: { code } }),
  twoFactorDisable: (password: string) => api("/auth/2fa/disable/", { method: "POST", json: { password } }),
  pushKey: () => api<{ public_key: string }>("/notifications/push/key/"),
  pushSubscribe: (sub: PushSubscriptionJSON) => api("/notifications/push/subscribe/", { method: "POST", json: sub }),
  pushUnsubscribe: (endpoint: string) => api("/notifications/push/subscribe/", { method: "DELETE", json: { endpoint } }),
  pushTest: () => api<{ devices: number }>("/notifications/push/test/", { method: "POST" }),
  notificationPrefs: () => api<NotificationPrefs>("/notifications/prefs/"),
  saveNotificationPrefs: (body: { email_unanswered: boolean }) => api<NotificationPrefs>("/notifications/prefs/", { method: "PUT", json: body }),
  auditLog: (page = 1, action = "") => api<{ results: AuditRow[]; has_more: boolean; page: number }>(`/audit-log/?page=${page}&action=${encodeURIComponent(action)}`),
  onboarding: () => api<Onboarding>("/onboarding/"),

  // commerce
  shopSettings: () => api<ShopSettings>("/shop/settings/"),
  saveShopSettings: (body: ShopSettingsInput) => api<ShopSettings>("/shop/settings/", { method: "PUT", json: body }),
  courierLookup: <T,>(courier: string, what: string, q = "") => api<T>(`/shop/couriers/${courier}/${what}/${q ? `?${q}` : ""}`),
  products: (q = "", active = false) => api<Product[]>(`/products/?q=${encodeURIComponent(q)}${active ? "&active=1" : ""}`),
  saveProduct: (id: number | null, body: Partial<Product>) =>
    api<Product>(id ? `/products/${id}/` : "/products/", { method: id ? "PUT" : "POST", json: body }),
  deleteProduct: (id: number) => api(`/products/${id}/`, { method: "DELETE" }),
  uploadProductImage: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api<{ id: string; url: string }>("/products/image/", { method: "POST", body: fd });
  },
  customers: (q = "") => api<Customer[]>(`/customers/?q=${encodeURIComponent(q)}`),
  customer: (id: string) => api<Customer>(`/customers/${id}/`),
  saveCustomer: (id: string | null, body: Partial<Customer>) =>
    api<Customer>(id ? `/customers/${id}/` : "/customers/", { method: id ? "PUT" : "POST", json: body }),
  mergeCustomer: (id: string, other_id: string) => api<Customer>(`/customers/${id}/merge/`, { method: "POST", json: { other_id } }),
  conversationCustomer: (conversationId: string) =>
    api<{ customer: Customer | null; orders: OrderSummary[]; suggested: { name: string; phone: string } | null }>(`/conversations/${conversationId}/customer/`),
  saveConversationCustomer: (conversationId: string, body: Partial<Customer>) =>
    api<{ customer: Customer | null; orders: OrderSummary[] }>(`/conversations/${conversationId}/customer/`, { method: "PUT", json: body }),
  orders: (params: Record<string, string> = {}) => api<OrderSummary[]>(`/orders/?${new URLSearchParams(params)}`),
  orderStats: () => api<OrderStats>("/orders/stats/"),
  order: (id: string) => api<Order>(`/orders/${id}/`),
  saveOrder: (id: string | null, body: OrderInput) =>
    api<Order>(id ? `/orders/${id}/` : "/orders/", { method: id ? "PUT" : "POST", json: body }),
  orderAction: (id: string, action: "status" | "payment-link" | "mark-paid" | "ship" | "send-summary", body: Record<string, unknown> = {}) =>
    api<Order>(`/orders/${id}/${action}/`, { method: "POST", json: body }),
  broadcasts: () => api<Broadcast[]>("/broadcasts/"),
  broadcast: (id: string) => api<Broadcast>(`/broadcasts/${id}/`),
  createBroadcast: (body: Partial<Broadcast> & { channel_id: string }) => api<Broadcast>("/broadcasts/", { method: "POST", json: body }),
  deleteBroadcast: (id: string) => api(`/broadcasts/${id}/`, { method: "DELETE" }),
  broadcastAction: (id: string, action: "send" | "cancel") => api<Broadcast>(`/broadcasts/${id}/${action}/`, { method: "POST" }),
  broadcastAudience: (channel_id: string, audience: BroadcastAudience) =>
    api<{ count: number; sample: string[]; note: string; kinds: string[]; opted_out: number }>("/broadcasts/audience/", { method: "POST", json: { channel_id, audience } }),
  whatsappTemplates: (channel: string) => api<WhatsAppTemplate[]>(`/broadcasts/templates/?channel=${channel}`),
  apiKeys: () => api<ApiKeyRow[]>("/developers/api-keys/"),
  createApiKey: (name: string) => api<ApiKeyRow>("/developers/api-keys/", { method: "POST", json: { name } }),
  revokeApiKey: (id: string) => api(`/developers/api-keys/${id}/`, { method: "DELETE" }),
  webhooks: () => api<{ events: Record<string, string>; endpoints: WebhookEndpoint[] }>("/developers/webhooks/"),
  saveWebhook: (id: string | null, body: Partial<WebhookEndpoint>) =>
    api<WebhookEndpoint>(id ? `/developers/webhooks/${id}/` : "/developers/webhooks/", { method: id ? "PUT" : "POST", json: body }),
  deleteWebhook: (id: string) => api(`/developers/webhooks/${id}/`, { method: "DELETE" }),
  testWebhook: (id: string) => api<{ ok: boolean; status: number | null; error: string; endpoint: WebhookEndpoint }>(`/developers/webhooks/${id}/test/`, { method: "POST" }),
  webhookDeliveries: (id: string) => api<WebhookDeliveryRow[]>(`/developers/webhooks/${id}/deliveries/`),
  saveBrand: (body: Partial<{ brand_name: string; brand_color: string; hide_powered_by: boolean }>) => api<Brand>("/workspace/brand/", { method: "PUT", json: body }),
  uploadBrandLogo: (file: File) => { const fd = new FormData(); fd.append("file", file); return api<Brand>("/workspace/brand/", { method: "POST", body: fd }); },
  removeBrandLogo: () => api<Brand>("/workspace/brand/", { method: "DELETE" }),
  publicPayment: (id: string) => api<PublicPayment>(`/pay/${id}/`),
  startPayment: (id: string, gateway: string) =>
    api<{ redirect_url?: string; form_url?: string; fields?: Record<string, string> }>(`/pay/${id}/start/${gateway}/`, { method: "POST" }),
  dismissOnboarding: (dismissed: boolean) => api<Onboarding>("/onboarding/", { method: "POST", json: { dismissed } }),
  me: () => api<Me>("/auth/me/"),
  logout: async () => {
    // Revoke the refresh token server-side, then forget both tokens locally.
    const refresh = auth.refresh;
    auth.clear();
    if (refresh) {
      await doFetch(`${API_BASE}/auth/logout/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      }).catch(() => undefined);
    }
  },
  logoutAll: () => api<{ ok: boolean }>("/auth/logout-all/", { method: "POST" }),
  updateMe: (body: { name?: string; current_password?: string; new_password?: string }) =>
    api<User>("/auth/me/", { method: "PATCH", json: body }),
  updateWorkspace: (body: Partial<Pick<Workspace, "name" | "agents_see_all" | "currency" | "unanswered_alert_minutes" | "sla_minutes" | "csat_enabled" | "csat_question">>) =>
    api<Workspace>("/workspace/", { method: "PATCH", json: body }),
  team: () => api<Team>("/team/"),
  invite: (email: string, role: Role) =>
    api<Invite & { emailed: boolean }>("/team/", { method: "POST", json: { email, role } }),
  revokeInvite: (id: string) => api(`/team/invites/${id}/`, { method: "DELETE" }),
  setRole: (userId: number, role: Role) => api<Member>(`/team/members/${userId}/`, { method: "PATCH", json: { role } }),
  removeMember: (userId: number) => api(`/team/members/${userId}/`, { method: "DELETE" }),
  inviteInfo: (token: string) =>
    api<{ workspace: string; email: string; role: Role; user_exists: boolean }>(`/invites/${token}/`),
  acceptInvite: (token: string, body: { name?: string; password: string }) =>
    api<{ access: string; refresh: string; workspace_id: string }>(`/invites/${token}/`, { method: "POST", json: body }),

  plans: () => api<Catalog>("/plans/"),
  billing: () => api<Billing>("/billing/"),
  checkout: (body: { plan: string; cycle: string; gateway: string; extra_seats: number }) =>
    api<{ redirect_url?: string; form_url?: string; fields?: Record<string, string>; amount: string; currency: string }>(
      "/billing/checkout/", { method: "POST", json: body }),
  addPromoCode: (code: string) => api<{ code: string }>("/billing/promo-code/", { method: "POST", json: { code } }),

  // affiliate program
  affiliateProgram: () =>
    api<{ rate: string; hold_days: number; min_payout: { NPR: string; USD: string } }>("/affiliates/program/"),
  affiliateCode: (code: string) =>
    api<{ valid: boolean; code: string; referrer: string }>(`/affiliates/code/${encodeURIComponent(code)}/`),
  affiliateClick: (body: { code: string; landing?: string; referrer?: string }) =>
    api<{ valid: boolean; code: string }>("/affiliates/click/", { method: "POST", json: body }),
  affiliateMe: () => api<AffiliateDashboard>("/affiliates/me/"),
  affiliateApply: (body: { code?: string; payout_method: PayoutMethod; payout_details: PayoutDetails; pitch?: string }) =>
    api<{ affiliate: AffiliateAccount }>("/affiliates/me/", { method: "POST", json: body }),
  affiliateUpdate: (body: { code?: string; payout_method?: PayoutMethod; payout_details?: PayoutDetails; pitch?: string }) =>
    api<{ affiliate: AffiliateAccount }>("/affiliates/me/", { method: "PATCH", json: body }),
  affiliatePayout: (currency: "NPR" | "USD") =>
    api<AffiliatePayout>("/affiliates/payouts/", { method: "POST", json: { currency } }),
  platformAffiliates: (params: { status?: string; q?: string } = {}) =>
    api<AdminAffiliateList>(`/platform/affiliates/?${new URLSearchParams(
      Object.entries(params).filter(([, v]) => v).map(([k, v]) => [k, String(v)]))}`),
  platformAffiliate: (id: number) => api<AdminAffiliateDetail>(`/platform/affiliates/${id}/`),
  platformAffiliateAction: (id: number, body: { action: "approve" | "reject" | "suspend" | "reactivate" | "set_rate"; note?: string; rate?: number }) =>
    api<AdminAffiliateDetail>(`/platform/affiliates/${id}/`, { method: "POST", json: body }),
  platformAffiliatePayouts: (status = "") =>
    api<AffiliatePayout[]>(`/platform/affiliate-payouts/${status ? `?status=${status}` : ""}`),
  platformPayoutAction: (id: number, body: { action: "paid" | "reject"; reference?: string; note?: string }) =>
    api<AffiliatePayout>(`/platform/affiliate-payouts/${id}/`, { method: "POST", json: body }),

  contactSales: (body: { name: string; email: string; company?: string; phone?: string; message: string }) =>
    api("/contact-sales/", { method: "POST", json: body }),

  tags: () => api<Tag[]>("/tags/"),
  createTag: (body: { name: string; color: string }) => api<Tag>("/tags/", { method: "POST", json: body }),
  deleteTag: (id: number) => api(`/tags/${id}/`, { method: "DELETE" }),
  canned: () => api<CannedReply[]>("/canned-replies/"),
  createCanned: (body: Omit<CannedReply, "id">) => api<CannedReply>("/canned-replies/", { method: "POST", json: body }),
  deleteCanned: (id: number) => api(`/canned-replies/${id}/`, { method: "DELETE" }),
  publishConfig: () => api<PublishConfig>("/publishing/config/"),
  socialAccounts: () => api<SocialAccount[]>("/publishing/accounts/"),
  connectFacebook: (body: { access_token: string; page_id?: string; via?: "facebook_login" }) =>
    api<{ accounts: SocialAccount[] }>("/publishing/accounts/facebook/", { method: "POST", json: body }),
  removeSocialAccount: (id: string) => api(`/publishing/accounts/${id}/`, { method: "DELETE" }),
  socialOAuthStart: (platform: "youtube" | "tiktok") =>
    api<{ url: string }>(`/publishing/oauth/${platform}/start/`, { method: "POST" }),
  posts: (params: Record<string, string> = {}) => api<SocialPost[]>(`/publishing/posts/?${new URLSearchParams(params)}`),
  savePost: (id: string | null, body: {
    caption: string; media_id: string | null; action: "draft" | "publish" | "schedule"; scheduled_at?: string | null;
    targets: Array<{ account_id: string; caption?: string; options?: PublishOptions }>;
  }) => api<SocialPost>(id ? `/publishing/posts/${id}/` : "/publishing/posts/", { method: id ? "PUT" : "POST", json: body }),
  post: (id: string) => api<SocialPost>(`/publishing/posts/${id}/`),
  tiktokCreator: (accountId: string) => api<TikTokCreator>(`/publishing/accounts/${accountId}/tiktok/`),
  aiPublishFill: (body: { media_id?: string | null; brief?: string; platforms: string[]; language: string }) =>
    api<PublishFill>("/ai/publish-fill/", { method: "POST", json: body }),
  deletePost: (id: string) => api(`/publishing/posts/${id}/`, { method: "DELETE" }),
  retryPost: (id: string) => api(`/publishing/posts/${id}/retry/`, { method: "POST" }),
  uploadMedia: (file: File, onProgress?: (pct: number) => void) =>
    new Promise<MediaAsset>((resolve, reject) => {
      // XHR (not fetch) so large videos can report upload progress
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/publishing/media/`);
      if (auth.access) xhr.setRequestHeader("Authorization", `Bearer ${auth.access}`);
      if (auth.workspace) xhr.setRequestHeader("X-Workspace-Id", auth.workspace);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
      xhr.onload = () => {
        let data: unknown = null;
        try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data as MediaAsset);
        else reject(new ApiError(xhr.status, data));
      };
      xhr.onerror = () => reject(new ApiError(0, "Upload failed. Check your connection."));
      const form = new FormData();
      form.append("file", file);
      xhr.send(form);
    }),
  analytics: (days: number) => api<Analytics>(`/analytics/?days=${days}`),
  downloadExport: async (days: number) => {
    const headers = new Headers();
    if (auth.access) headers.set("Authorization", `Bearer ${auth.access}`);
    if (auth.workspace) headers.set("X-Workspace-Id", auth.workspace);
    const res = await doFetch(`${API_BASE}/analytics/export.csv?days=${days}`, { headers });
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `conversations-${days}d.csv` });
    a.click();
    URL.revokeObjectURL(url);
  },

  providers: () => api<ProviderMeta[]>("/providers/"),
  metaConfig: () => api<MetaConfig>("/meta/config/"),
  metaWhatsApp: (body: { code: string; waba_id: string; phone_number_id: string; pin?: string }) =>
    api<Channel>("/meta/whatsapp/", { method: "POST", json: body }),
  metaPages: (accessToken: string) =>
    api<{ session: string; pages: MetaPage[] }>("/meta/pages/", { method: "POST", json: { access_token: accessToken } }),
  metaPagesConnect: (body: { session: string; pages: string[]; instagram: string[] }) =>
    api<Channel[]>("/meta/pages/connect/", { method: "POST", json: body }),
  platformOverview: () => api<PlatformOverview>("/platform/overview/"),
  platformInsights: () => api<PlatformInsights>("/platform/insights/"),
  platformWorkspaces: (params: { q?: string; filter?: string; offset?: number }) =>
    api<{ count: number; results: PlatformWorkspace[] }>(`/platform/workspaces/?${new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]))}`),
  platformWorkspace: (id: string) => api<PlatformWorkspaceDetail>(`/platform/workspaces/${id}/`),
  platformAction: (id: string, body: { action: "suspend" | "unsuspend" | "extend"; reason?: string; days?: number; plan?: string }) =>
    api<PlatformWorkspaceDetail>(`/platform/workspaces/${id}/`, { method: "POST", json: body }),
  setLanguage: (language: "en" | "ne") => api("/auth/me/", { method: "PATCH", json: { language } }),
  channels: () => api<Channel[]>("/channels/"),
  createChannel: (body: { provider: string; name: string; credentials: Record<string, string> }) =>
    api<Channel>("/channels/", { method: "POST", json: body }),
  updateChannel: (id: string, body: Partial<{ name: string; credentials: Record<string, string> }>) =>
    api<Channel>(`/channels/${id}/`, { method: "PATCH", json: body }),
  deleteChannel: (id: string) => api(`/channels/${id}/`, { method: "DELETE" }),
  testChannel: (id: string) => api<{ channel: Channel }>(`/channels/${id}/test/`, { method: "POST" }),
  syncChannel: (id: string) => api<{ new_messages: number; channel: Channel }>(`/channels/${id}/sync/`, { method: "POST" }),
  oauthStart: (id: string) => api<{ url: string }>(`/channels/${id}/oauth/start/`, { method: "POST" }),
  loadDemo: () => api<{ created: number }>("/channels/demo/", { method: "POST" }),
  clearDemo: () => api("/channels/demo/clear/", { method: "DELETE" }),

  stats: () => api<Stats>("/stats/"),
  conversations: (params: Record<string, string>) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null));
    return api<Paginated<Conversation>>(`/conversations/?${q.toString()}`);
  },
  conversation: (id: string) => api<Conversation>(`/conversations/${id}/`),
  updateConversation: (id: string, body: { status?: string; assigned_to_id?: number | null; tag_ids?: number[] }) =>
    api<Conversation>(`/conversations/${id}/`, { method: "PATCH", json: body }),
  messages: (id: string, after?: string) =>
    api<Message[]>(`/conversations/${id}/messages/${after ? `?after=${encodeURIComponent(after)}` : ""}`),
  send: (id: string, text: string, note = false, attachmentIds: string[] = []) =>
    api<Message>(`/conversations/${id}/messages/`, { method: "POST", json: { text, note, attachment_ids: attachmentIds } }),
  uploadAttachment: (file: Blob, name: string, kind = "", onProgress?: (pct: number) => void) =>
    new Promise<Attachment>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/attachments/`);
      if (auth.access) xhr.setRequestHeader("Authorization", `Bearer ${auth.access}`);
      if (auth.workspace) xhr.setRequestHeader("X-Workspace-Id", auth.workspace);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
      xhr.onload = () => {
        let data: unknown = null;
        try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data as Attachment);
        else reject(new ApiError(xhr.status, data));
      };
      xhr.onerror = () => reject(new ApiError(0, "Upload failed. Check your connection."));
      const form = new FormData();
      form.append("file", file, name);
      if (kind) form.append("kind", kind);
      xhr.send(form);
    }),
  events: (v: string, signal?: AbortSignal) =>
    api<{ v: string; changed: boolean }>(`/events/?v=${encodeURIComponent(v)}`, { signal }),
  markRead: (id: string) => api(`/conversations/${id}/read/`, { method: "POST" }),
  privateReply: (id: string, text: string) => api<Message>(`/conversations/${id}/private-reply/`, { method: "POST", json: { text } }),
  setBotPaused: (id: string, paused: boolean) =>
    api<Conversation>(`/conversations/${id}/bot/`, { method: "POST", json: { paused } }),

  // AI & automations
  aiSettings: () => api<AISettings>("/ai/settings/"),
  aiReport: (hours = 24) => api<AIReport>(`/ai/report/?hours=${hours}`),
  paymentChecks: (params: { conversation?: string; status?: string } = {}) =>
    api<PaymentCheck[]>(`/payment-checks/?${new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][])}`),
  confirmPaymentCheck: (id: number, orderId?: string) => api<PaymentCheck>(`/payment-checks/${id}/confirm/`, { method: "POST", json: orderId ? { order_id: orderId } : {} }),
  rejectPaymentCheck: (id: number, message = "") => api<PaymentCheck>(`/payment-checks/${id}/reject/`, { method: "POST", json: { message } }),
  bookings: (params: { from?: string; to?: string; status?: string } = {}) =>
    api<Booking[]>(`/bookings/?${new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][])}`),
  createBooking: (body: BookingInput) => api<Booking>("/bookings/", { method: "POST", json: body }),
  updateBooking: (id: string, body: BookingInput) => api<Booking>(`/bookings/${id}/`, { method: "PATCH", json: body }),
  deleteBooking: (id: string) => api<void>(`/bookings/${id}/`, { method: "DELETE" }),
  saveAISettings: (body: Partial<AISettings>) => api<AISettings>("/ai/settings/", { method: "PUT", json: body }),
  knowledge: () => api<KnowledgeItem[]>("/ai/knowledge/"),
  saveKnowledge: (id: number | null, body: { title: string; content: string }) =>
    api<KnowledgeItem>(id ? `/ai/knowledge/${id}/` : "/ai/knowledge/", { method: id ? "PUT" : "POST", json: body }),
  deleteKnowledge: (id: number) => api(`/ai/knowledge/${id}/`, { method: "DELETE" }),
  knowledgeSources: () => api<KnowledgeSource[]>("/ai/knowledge/sources/"),
  importWebsite: (url: string, crawl: boolean) =>
    api<KnowledgeSource>("/ai/knowledge/sources/url/", { method: "POST", json: { url, crawl } }),
  resyncSource: (id: number) => api<KnowledgeSource>(`/ai/knowledge/sources/${id}/`, { method: "POST" }),
  deleteSource: (id: number) => api(`/ai/knowledge/sources/${id}/`, { method: "DELETE" }),
  searchKnowledge: (q: string) => api<KnowledgeMatch[]>(`/ai/knowledge/search/?q=${encodeURIComponent(q)}`),
  uploadKnowledge: (file: File, onProgress?: (pct: number) => void) =>
    new Promise<KnowledgeSource>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/ai/knowledge/sources/upload/`);
      if (auth.access) xhr.setRequestHeader("Authorization", `Bearer ${auth.access}`);
      if (auth.workspace) xhr.setRequestHeader("X-Workspace-Id", auth.workspace);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
      xhr.onload = () => {
        let data: unknown = null;
        try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data as KnowledgeSource);
        else reject(new ApiError(xhr.status, data));
      };
      xhr.onerror = () => reject(new ApiError(0, "Upload failed. Check your connection."));
      const form = new FormData();
      form.append("file", file);
      xhr.send(form);
    }),
  aiSuggest: (conversation_id: string, instruction = "") =>
    api<{ reply: string; confidence: "high" | "low"; missing: string; sources?: KnowledgeRef[] }>("/ai/suggest/", { method: "POST", json: { conversation_id, instruction } }),
  aiRewrite: (text: string, mode: RewriteMode) => api<{ text: string }>("/ai/rewrite/", { method: "POST", json: { text, mode } }),
  aiSummary: (conversation_id: string) => api<AISummary>("/ai/summary/", { method: "POST", json: { conversation_id } }),
  aiCaption: (body: { brief: string; platforms: string[]; tone?: string; language?: string }) =>
    api<{ captions: Record<string, string>; title: string }>("/ai/caption/", { method: "POST", json: body }),
  aiPlayground: (message: string) => api<BotAnswer>("/ai/playground/", { method: "POST", json: { message } }),
  rules: () => api<AutomationRule[]>("/automations/rules/"),
  saveRule: (id: string | null, body: RuleInput) =>
    api<AutomationRule>(id ? `/automations/rules/${id}/` : "/automations/rules/", { method: id ? "PUT" : "POST", json: body }),
  deleteRule: (id: string) => api(`/automations/rules/${id}/`, { method: "DELETE" }),
};
