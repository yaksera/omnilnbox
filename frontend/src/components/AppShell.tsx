"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  BarChart3, Check, CircleHelp, Gift, ShoppingBag, Contact, RadioTower, CreditCard, Inbox, LoaderCircle, LogOut, MailWarning, Megaphone, Bot, Languages, Plug, Rocket, Settings, ShieldCheck, ShieldOff, Sparkles, Users, CalendarCheck } from "lucide-react";
import { subscribe } from "@/lib/realtime";
import { useLang, useT } from "@/lib/i18n";
import { Api, auth } from "@/lib/api";
import type { Capability, Me } from "@/lib/types";
import { avatarColor, initials } from "@/lib/format";
import { daysLeft, ROLE_LABELS } from "@/lib/money";
import { chime, desktopAlert, localPrefs, registerWorker } from "@/lib/notifications";
import MobileNav from "@/components/mobile/MobileNav";

type Ctx = { me: Me; reloadMe: () => Promise<void>; can: (c: Capability) => boolean; hasFeature: (f: string) => boolean };
const MeContext = createContext<Ctx | null>(null);

/** Pages can hide the phone tab bar (e.g. while a conversation is open, so the reply box has room). */
const MobileChromeContext = createContext<{ setTabBarHidden: (hidden: boolean) => void }>({ setTabBarHidden: () => undefined });
export function useMobileChrome() {
  return useContext(MobileChromeContext);
}

export function useMe() {
  const ctx = useContext(MeContext);
  if (!ctx) throw new Error("useMe outside AppShell");
  return ctx;
}

const NAV: Array<{ href: string; label: string; icon: typeof Inbox; cap?: Capability }> = [
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/orders", label: "Orders", icon: ShoppingBag },
  { href: "/customers", label: "Customers", icon: Contact },
  { href: "/visits", label: "Visits", icon: CalendarCheck },
  { href: "/publish", label: "Publish", icon: Megaphone },
  { href: "/broadcasts", label: "Broadcast", icon: RadioTower },
  { href: "/automations", label: "AI", icon: Bot },
  { href: "/analytics", label: "Analytics", icon: BarChart3, cap: "view_analytics" },
  { href: "/channels", label: "Channels", icon: Plug },
  { href: "/team", label: "Team", icon: Users },
  { href: "/billing", label: "Billing", icon: CreditCard },
  { href: "/settings", label: "Settings", icon: Settings },
];

function PlanBanner({ me }: { me: Me }) {
  const t = useT();
  const ws = me.workspace;
  const isOwner = me.role === "owner";
  if (ws.is_trialing) {
    const d = daysLeft(ws.trial_ends_at);
    return (
      <div className="flex items-center justify-center gap-2 bg-brand-600 px-4 py-1.5 text-center text-xs text-white">
        <Sparkles size={14} /> {t(d === 1 ? "{d} day left in your {plan} trial." : "{d} days left in your {plan} trial.", { d, plan: ws.plan_name })}
        {isOwner && <Link href="/billing" className="font-semibold underline underline-offset-2">{t("Choose a plan")}</Link>}
      </div>
    );
  }
  if (ws.is_expired) {
    return (
      <div className="bg-amber-500 px-4 py-1.5 text-center text-xs font-medium text-amber-950">
        {t("Your plan has ended, so Free plan limits apply.")}{" "}
        {isOwner ? <Link href="/billing" className="underline underline-offset-2">{t("Renew now")}</Link> : t("Ask the workspace owner to renew.")}
      </div>
    );
  }
  return null;
}

/** White-label: recolour the app from the brand colour (Tailwind v4 theme colours are CSS variables). */
function mix(hex: string, target: number, amount: number) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [n >> 16, (n >> 8) & 255, n & 255].map((c) => Math.round(c + (target - c) * amount));
  return `#${ch.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}
function useBrandTheme(color: string) {
  useEffect(() => {
    const root = document.documentElement.style;
    const keys = ["50", "100", "300", "500", "600", "700"];
    if (!/^#[0-9a-fA-F]{6}$/.test(color)) { keys.forEach((k) => root.removeProperty(`--color-brand-${k}`)); return; }
    const shades: Record<string, string> = { "50": mix(color, 255, 0.93), "100": mix(color, 255, 0.86), "300": mix(color, 255, 0.55),
      "500": mix(color, 255, 0.15), "600": color, "700": mix(color, 0, 0.15) };
    keys.forEach((k) => root.setProperty(`--color-brand-${k}`, shades[k]));
  }, [color]);
}

function VerifyBanner({ me }: { me: Me }) {
  const t = useT();
  const [state, setState] = useState<{ sent: boolean; link?: string; busy: boolean }>({ sent: false, busy: false });
  if (me.user.email_verified) return null;
  return (
    <div className="flex flex-wrap items-center justify-center gap-2 bg-amber-100 px-4 py-1.5 text-center text-xs text-amber-900">
      <MailWarning size={14} /> {t("Please confirm your email")} <b className="hidden sm:inline">{me.user.email}</b> <span className="hidden sm:inline">{t("so you can reset your password and get alerts.")}</span>
      {state.sent ? (
        state.link ? <a className="font-semibold underline" href={state.link}>Dev mode: open the confirmation link</a> : <span className="font-semibold">{t("Sent! Check your inbox.")}</span>
      ) : (
        <button type="button" className="font-semibold underline underline-offset-2" disabled={state.busy}
          onClick={async () => {
            setState({ ...state, busy: true });
            const r = await Api.sendVerification().catch(() => null);
            setState({ sent: true, busy: false, link: r?.dev_link });
          }}>{t("Resend email")}</button>
      )}
    </div>
  );
}

/** Setup progress ring in the sidebar (hidden when done or dismissed). */
function SetupProgress() {
  const t = useT();
  const [p, setP] = useState<{ done: number; total: number; dismissed: boolean } | null>(null);
  const pathname = usePathname();
  useEffect(() => { Api.onboarding().then(setP).catch(() => undefined); }, [pathname]);
  if (!p || p.dismissed || p.done >= p.total) return null;
  const pct = p.done / p.total, r = 15, c = 2 * Math.PI * r;
  return (
    <Link href="/get-started" title={`Setup: ${p.done} of ${p.total} done`}
      className={clsx("flex shrink-0 flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 md:w-14", pathname === "/get-started" ? "bg-slate-800 text-white" : "hover:bg-slate-900 hover:text-white")}>
      <span className="relative flex h-[22px] w-[22px] items-center justify-center">
        <svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90" aria-hidden>
          <circle cx="18" cy="18" r={r} fill="none" stroke="#334155" strokeWidth="4" />
          <circle cx="18" cy="18" r={r} fill="none" stroke="#818cf8" strokeWidth="4" strokeDasharray={`${c * pct} ${c}`} strokeLinecap="round" />
        </svg>
        <Rocket size={11} />
      </span>
      <span className="hidden text-[10px] font-medium md:block">{t("Setup")} {p.done}/{p.total}</span>
    </Link>
  );
}

function WorkspaceMenu({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const t = useT();
  const { lang, setLang } = useLang();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function switchTo(id: string) {
    auth.setWorkspace(id);
    // Full reload so every page re-fetches data for the new workspace
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/inbox");
  }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1 rounded-full" aria-label="Account menu">
        <span className="flex h-9 w-9 items-center justify-center rounded-full text-xs font-semibold text-white" style={{ background: avatarColor(me.user.email) }}>
          {initials(me.user.name)}
        </span>
      </button>
      {open && (
        <div className="absolute bottom-auto right-0 top-11 z-50 w-64 rounded-xl border border-slate-200 bg-white p-1.5 text-slate-800 shadow-xl md:bottom-0 md:left-12 md:right-auto md:top-auto">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-semibold">{me.user.name}</p>
            <p className="truncate text-xs text-slate-500">{me.user.email}</p>
          </div>
          <div className="my-1 border-t border-slate-100" />
          <div className="flex items-center justify-between gap-2 px-3 py-1.5 text-sm">
            <span className="flex items-center gap-2 text-slate-600"><Languages size={16} /> {t("Language")}</span>
            <span className="flex rounded-lg bg-slate-100 p-0.5 text-xs">
              {(["en", "ne"] as const).map((l) => (
                <button key={l} type="button" onClick={() => { setLang(l); Api.setLanguage(l).catch(() => undefined); }}
                  className={clsx("rounded-md px-2 py-1 font-medium", lang === l ? "bg-white shadow-sm" : "text-slate-500")}>{l === "en" ? "English" : "नेपाली"}</button>
              ))}
            </span>
          </div>
          <div className="my-1 border-t border-slate-100" />
          <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{t("Workspaces")}</p>
          {me.memberships.map((m) => (
            <button key={m.workspace.id} onClick={() => switchTo(m.workspace.id)}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{m.workspace.name}</span>
                <span className="text-xs text-slate-500">{ROLE_LABELS[m.role]} · {m.workspace.plan_name}</span>
              </span>
              {m.workspace.id === me.workspace.id && <Check size={16} className="text-brand-600" />}
            </button>
          ))}
          <div className="my-1 border-t border-slate-100" />
          <Link href="/settings" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-slate-50"><Settings size={16} /> {t("Profile & settings")}</Link>
          <Link href="/affiliate" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-slate-50"><Gift size={16} /> {t("Refer & earn")}</Link>
          <button onClick={onLogout} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"><LogOut size={16} /> {t("Log out")}</button>
        </div>
      )}
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const t = useT();
  const { lang, setLang } = useLang();
  const langSynced = useRef(false);
  const [unread, setUnread] = useState(0);
  const [tabBarHidden, setTabBarHidden] = useState(false);
  useEffect(() => {
    // the language saved on the account wins once per load (e.g. logging in on a new phone)
    if (me && !langSynced.current) {
      langSynced.current = true;
      if (me.user.language && me.user.language !== lang) setLang(me.user.language);
    }
  }, [me, lang, setLang]);

  const reloadMe = useCallback(async () => {
    const data = await Api.me();
    if (!auth.workspace) auth.setWorkspace(data.workspace.id);
    setMe(data);
  }, []);

  useEffect(() => {
    if (!auth.isLoggedIn()) {
      router.replace("/login");
      return;
    }
    reloadMe().catch(() => {
      // a stale workspace id (e.g. removed from a workspace) -> fall back to the default one
      if (auth.workspace) {
        auth.setWorkspace("");
        reloadMe().catch(() => router.replace("/login"));
      } else router.replace("/login");
    });
  }, [reloadMe, router]);

  useBrandTheme(me?.workspace.brand?.color ?? "");

  // New-message sound + desktop alert, and open conversations tapped in a push notification
  const lastUnread = useRef<number | null>(null);
  useEffect(() => {
    if (!me) return;
    registerWorker();
    const onMsg = (e: MessageEvent) => {
      // full navigation so the inbox opens the tapped conversation even if it's already on screen
      if (e.data?.type === "open" && typeof e.data.url === "string") window.location.assign(e.data.url);
    };
    navigator.serviceWorker?.addEventListener("message", onMsg);
    const tick = async () => {
      const s = await Api.stats().catch(() => null);
      if (!s) return;
      const prev = lastUnread.current;
      lastUnread.current = s.unread_messages;
      setUnread(s.unread_conversations);
      if (prev !== null && s.unread_messages > prev) {
        const prefs = localPrefs();
        if (prefs.sound) chime();
        if (prefs.desktop) desktopAlert("New customer message", `${s.unread_messages} unread message${s.unread_messages === 1 ? "" : "s"} in ${me.workspace.name}`);
        document.title = `(${s.unread_messages}) OmniInbox`;
      } else if (s.unread_messages === 0) document.title = "OmniInbox";
    };
    tick();
    const t = setInterval(() => { tick(); }, 60000);  // safety net; live updates call tick() instantly
    const unsubscribe = subscribe(() => { tick(); });
    return () => { clearInterval(t); unsubscribe(); navigator.serviceWorker?.removeEventListener("message", onMsg); };
  }, [me, router]);

  if (!me) {
    return <div className="flex h-screen items-center justify-center text-slate-400"><LoaderCircle className="animate-spin" /></div>;
  }

  async function logout() {
    await Api.logout();
    router.replace("/login");
  }

  const can = (c: Capability) => me.capabilities.includes(c);
  const hasFeature = (f: string) => me.workspace.features.includes(f);
  const nav = [...NAV.filter((n) => !n.cap || can(n.cap)),
    ...(me.user.is_platform_admin ? [{ href: "/admin-panel", label: "Admin", icon: ShieldCheck }] : [])];

  if (me.workspace.suspended) {
    const others = me.memberships.filter((m) => m.workspace.id !== me.workspace.id && !m.workspace.suspended);
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="card max-w-md p-8 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600"><ShieldOff size={24} /></span>
          <h1 className="mt-4 text-lg font-semibold">{t("{name} is suspended", { name: me.workspace.name })}</h1>
          <p className="mt-2 text-sm text-slate-600">{t("This workspace has been suspended by OmniInbox, so its inbox, channels, website chat and payment links are paused. Nothing has been deleted.")}</p>
          {me.workspace.suspended.reason && <p className="mt-3 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">{t("Reason: {reason}", { reason: me.workspace.suspended.reason })}</p>}
          <p className="mt-3 text-sm text-slate-600"><a href="/contact" className="font-medium text-brand-700 hover:underline">{t("Please contact OmniInbox support to reactivate it.")}</a></p>
          <div className="mt-6 flex flex-col gap-2">
            {others.map((m) => (
              // eslint-disable-next-line @next/next/no-location-assign-relative-destination
              <button key={m.workspace.id} className="btn-secondary" onClick={() => { auth.setWorkspace(m.workspace.id); window.location.assign("/inbox"); }}>
                {t("Switch to {name}", { name: m.workspace.name })}
              </button>
            ))}
            <button className="btn-ghost text-red-600" onClick={logout}><LogOut size={16} /> Log out</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <MeContext.Provider value={{ me, reloadMe, can, hasFeature }}>
     <MobileChromeContext.Provider value={{ setTabBarHidden }}>
      <div className="pt-safe flex h-[100dvh] flex-col md:h-screen">
        <PlanBanner me={me} />
        <VerifyBanner me={me} />
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside className="hidden shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-3 py-2 text-slate-400 md:flex md:w-[68px] md:flex-col md:border-b-0 md:border-r md:py-4">
            <div className="scroll-thin flex min-h-0 items-center gap-1 overflow-x-auto md:flex-col md:gap-1 md:overflow-y-auto md:overflow-x-hidden">
              <Link href="/inbox" className="mr-1 flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white md:mb-4 md:mr-0" title={me.workspace.brand?.name || "OmniInbox"}>
                {me.workspace.brand?.logo_url
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={me.workspace.brand.logo_url} alt="" className="h-full w-full bg-white object-contain" />
                  : <Inbox size={18} strokeWidth={2.4} />}
              </Link>
              {nav.map((n) => {
                const active = pathname.startsWith(n.href);
                return (
                  <Link key={n.href} href={n.href} title={t(n.label)}
                    className={clsx("group flex shrink-0 flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 transition md:w-14",
                      active ? "bg-slate-800 text-white" : "hover:bg-slate-900 hover:text-white")}>
                    <n.icon size={19} />
                    <span className="hidden text-[10px] font-medium md:block">{t(n.label)}</span>
                  </Link>
                );
              })}
            </div>
            <div className="flex items-center gap-2 md:flex-col">
              <SetupProgress />
              <a href="/docs" target="_blank" rel="noopener" title={t("Help center")} className="flex shrink-0 flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 hover:bg-slate-900 hover:text-white md:w-14">
                <CircleHelp size={19} /><span className="hidden text-[10px] font-medium md:block">{t("Help")}</span>
              </a>
              <span className="hidden rounded-md bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-300 md:block" title={t("Current plan")}>
                {me.workspace.plan_name}
              </span>
              <WorkspaceMenu me={me} onLogout={logout} />
              <button type="button" onClick={logout} title={t("Log out")} aria-label={t("Log out")}
                className="flex shrink-0 flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 hover:bg-slate-900 hover:text-white md:w-14">
                <LogOut size={19} /><span className="hidden text-[10px] font-medium md:block">{t("Log out")}</span>
              </button>
            </div>
          </aside>
          <main className={clsx("min-h-0 min-w-0 flex-1 md:pb-0", !tabBarHidden && "pb-[calc(4.25rem+env(safe-area-inset-bottom))]")}>{children}</main>
        </div>
        <MobileNav me={me} links={nav} unread={unread} onLogout={logout} hidden={tabBarHidden} />
      </div>
     </MobileChromeContext.Provider>
    </MeContext.Provider>
  );
}

export function UpgradeHint({ feature, children }: { feature: string; children?: React.ReactNode }) {
  const { me } = useMe();
  const t = useT();
  return (
    <div className="rounded-xl border border-dashed border-brand-300 bg-brand-50/50 p-4 text-sm text-slate-700">
      <p className="flex items-center gap-2 font-medium text-brand-700"><Sparkles size={16} /> {t("{feature} is on a higher plan", { feature })}</p>
      <p className="mt-1 text-slate-600">{children}</p>
      {me.role === "owner"
        ? <Link href="/billing" className="btn-primary mt-3 px-3 py-1.5">{t("See plans")}</Link>
        : <p className="mt-2 text-xs text-slate-500">{t("Ask the workspace owner to upgrade.")}</p>}
    </div>
  );
}

