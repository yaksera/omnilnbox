"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { Ban, Bot, CalendarPlus, Gift, LoaderCircle, MessagesSquare, RotateCcw, Search, ShieldCheck, Users, X } from "lucide-react";
import { Api } from "@/lib/api";
import type { PlatformInsights, PlatformOverview, PlatformWorkspace, PlatformWorkspaceDetail } from "@/lib/types";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { useMe } from "@/components/AppShell";
import { timeAgo } from "@/lib/format";
import { useT } from "@/lib/i18n";

const FILTERS = [
  ["all", "All"], ["paying", "Paying"], ["trial", "On trial"], ["trial_ending", "Trial ends ≤ 7 days"],
  ["expired", "Expired"], ["free", "Free"], ["suspended", "Suspended"],
] as const;

const STATUS_STYLE: Record<PlatformWorkspace["status"], string> = {
  paying: "bg-emerald-50 text-emerald-700", trial: "bg-sky-50 text-sky-700", expired: "bg-amber-50 text-amber-800",
  free: "bg-slate-100 text-slate-600", suspended: "bg-red-50 text-red-700", internal: "bg-violet-50 text-violet-700",
};
const STATUS_LABEL: Record<PlatformWorkspace["status"], string> = {
  paying: "Paying", trial: "Trial", expired: "Expired", free: "Free", suspended: "Suspended", internal: "Yours (internal)",
};

const npr = (v: string) => `Rs ${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const usd = (v: string) => `$${Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const date = (v: string | null) => (v ? new Date(v).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");

function Tile({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: "warn" | "bad" }) {
  const t = useT();
  return (
    <div className="card p-4">
      <p className="text-xs font-medium text-slate-500">{t(label)}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      {sub && <p className={clsx("mt-0.5 text-xs", tone === "bad" ? "text-red-600" : tone === "warn" ? "text-amber-700" : "text-slate-500")}>{sub}</p>}
    </div>
  );
}

/** Single-series bar chart (one hue, recessive axis, hover tooltip per bar). */
function Bars({ title, points, format }: { title: string; points: Array<{ label: string; value: number }>; format: (n: number) => string }) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...points.map((p) => p.value));
  const total = points.reduce((s, p) => s + p.value, 0);
  return (
    <div className="card p-4">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-slate-900">{t(title)}</p>
        <p className="text-xs tabular-nums text-slate-500">{hover !== null ? `${points[hover].label}: ${format(points[hover].value)}` : t("Total {value}", { value: format(total) })}</p>
      </div>
      {points.length === 0 ? <p className="mt-6 pb-6 text-center text-sm text-slate-400">{t("No data yet")}</p> : (
        <div className="mt-3 flex h-32 items-end gap-[2px] border-b border-slate-200" role="img" aria-label={`${t(title)}: ${points.map((p) => `${p.label} ${format(p.value)}`).join(", ")}`}>
          {points.map((p, i) => (
            <div key={p.label} className="flex h-full flex-1 cursor-default items-end" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <div className={clsx("w-full rounded-t-[4px] transition-colors", hover === i ? "bg-brand-700" : "bg-brand-500")}
                style={{ height: `${Math.max(p.value ? 3 : 0, (p.value / max) * 100)}%` }} />
            </div>
          ))}
        </div>
      )}
      {points.length > 0 && (
        <div className="mt-1 flex justify-between text-[10px] text-slate-400"><span>{points[0].label}</span><span>{points[points.length - 1].label}</span></div>
      )}
    </div>
  );
}

const num = (n: number) => n.toLocaleString("en-IN");
const tokens = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(0)}K` : String(n));
const both = (m: { NPR: string; USD: string }) => (Number(m.USD) ? `${npr(m.NPR)} + ${usd(m.USD)}` : npr(m.NPR));

function SectionTitle({ icon: Icon, title, children }: { icon: typeof Users; title: string; children?: React.ReactNode }) {
  const t = useT();
  return (
    <div className="flex flex-wrap items-end justify-between gap-2 pt-2">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900"><Icon size={18} className="text-brand-600" /> {t(title)}</h2>
      {children}
    </div>
  );
}

/** Users, AI usage, affiliates and activity across the whole platform. */
function Insights({ today }: { today: number }) {
  const t = useT();
  const [d, setD] = useState<PlatformInsights | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { Api.platformInsights().then(setD).catch((e) => setError(e.message)); }, []);
  if (error) return <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>;
  if (!d) return <div className="flex justify-center p-10 text-slate-400"><LoaderCircle className="animate-spin" /></div>;
  const { users: u, ai, affiliates: a, activity: act, funnel } = d;
  const byDay = new Map(u.signups_by_day.map((x) => [x.day, x.count]));
  const signupDays = Array.from({ length: 30 }, (_, i) => {
    const day = new Date(today - (29 - i) * 86400000).toISOString().slice(0, 10);
    return { label: new Date(day).toLocaleDateString(undefined, { day: "numeric", month: "short" }), value: byDay.get(day) ?? 0 };
  });
  const monthName = new Date(`${ai.month}T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" });
  return (
    <>
      <SectionTitle icon={Users} title="Users & sign-ups" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="New sign-ups today" value={u.signups.today} sub={t("{a} this week · {b} in 30 days", { a: u.signups.d7, b: u.signups.d30 })} />
        <Tile label="User accounts" value={num(u.total)} sub={t("{n} confirmed their email", { n: u.verified })} />
        <Tile label="Active users" value={u.active.d7} sub={t("logged in this week · {n} today · {m} in 30 days", { n: u.active.d1, m: u.active.d30 })} />
        <Tile label="Trial → paid" value={`${funnel.conversion}%`} sub={t("{paid} of {total} new workspaces paid (90 days)", { paid: funnel.paid_90d, total: funnel.created_90d })} />
      </div>
      <div className="grid items-start gap-3 lg:grid-cols-2">
        <Bars title="New user sign-ups (last 30 days)" points={signupDays} format={(n) => `${n}`} />
        <div className="card overflow-hidden">
          <p className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">{t("Latest sign-ups")}</p>
          <ul className="divide-y divide-slate-100 text-sm">
            {u.recent.map((r) => (
              <li key={r.email} className="flex items-center gap-2 px-4 py-2">
                <span className="min-w-0 flex-1"><span className="block truncate font-medium text-slate-800">{r.name}</span>
                  <span className="block truncate text-xs text-slate-500">{r.email}{r.workspace ? ` · ${r.workspace}` : ""}</span></span>
                <span className="shrink-0 text-xs text-slate-500">{timeAgo(r.joined)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <SectionTitle icon={Bot} title="AI usage">
        <p className="text-xs text-slate-500">{t("Model {model} · cost is an estimate at ${rate} per 1M tokens", { model: ai.model, rate: ai.cost_per_million_usd })}</p>
      </SectionTitle>
      {!ai.configured && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{t("AI is off: add OPENROUTER_API_KEY to backend/.env.")}</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="AI credits used" value={num(ai.credits)} sub={t("{month} · {n} workspaces", { month: monthName, n: ai.workspaces_using })} />
        <Tile label="Tokens used" value={tokens(ai.tokens)} sub={t("≈ {cost} this month", { cost: `$${ai.cost_usd}` })} />
        <Tile label="AI chatbot replies" value={num(ai.bot_replies.d30)} sub={t("{n} today · {h} handed to a human", { n: ai.bot_replies.d1, h: ai.handoffs_30d })} />
        <Tile label="Near their AI limit" value={ai.near_limit} sub={t("workspaces at 90%+ of monthly credits")} tone={ai.near_limit ? "warn" : undefined} />
      </div>
      <div className="grid items-start gap-3 lg:grid-cols-2">
        <Bars title="AI credits by month" points={ai.by_month.map((m) => ({ label: m.month, value: m.credits }))} format={(n) => num(n)} />
        <div className="card overflow-hidden">
          <p className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">{t("Top AI users this month")}</p>
          {ai.top.length === 0 ? <p className="p-4 text-sm text-slate-500">{t("No AI usage yet this month.")}</p> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {ai.top.map((w) => {
                const pct = w.limit ? Math.min(100, Math.round((w.credits / w.limit) * 100)) : 0;
                return (
                  <li key={w.id} className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate font-medium text-slate-800">{w.name} <span className="font-normal text-slate-500">· {w.plan}</span></span>
                      <span className="text-xs tabular-nums text-slate-600">{num(w.credits)} / {num(w.limit)} · {tokens(w.tokens)} · ${w.cost_usd}</span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div className={clsx("h-full rounded-full", pct >= 90 ? "bg-amber-500" : "bg-brand-500")} style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      <SectionTitle icon={Gift} title="Affiliates">
        <Link href="/admin-panel/affiliates" className="text-sm font-medium text-brand-600 hover:text-brand-700">{t("Manage affiliates →")}</Link>
      </SectionTitle>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Affiliates" value={a.approved} sub={t("{p} waiting for approval · {s} suspended", { p: a.pending, s: a.suspended })} tone={a.pending ? "warn" : undefined} />
        <Tile label="Referred sign-ups" value={a.referrals} sub={t("{n} in 30 days · {c} link clicks", { n: a.referrals_30d, c: a.clicks_30d })} />
        <Tile label="Referred & paying" value={a.paying_referrals} sub={t("currently subscribed")} />
        <Tile label="Commission owed" value={both(a.owed)} sub={t("paid so far {amount} · {n} payout requests", { amount: both(a.paid), n: a.payouts_requested })} tone={a.payouts_requested ? "warn" : undefined} />
      </div>
      {a.top.length > 0 && (
        <div className="card overflow-hidden">
          <p className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">{t("Top affiliates")}</p>
          <ul className="divide-y divide-slate-100 text-sm">
            {a.top.map((x) => (
              <li key={x.id} className="flex items-center gap-3 px-4 py-2">
                <span className="flex-1 font-medium text-slate-800">{x.name} <span className="font-mono text-xs font-normal text-slate-500">{x.code}</span></span>
                <span className="text-xs text-slate-500">{t("{n} sign-ups", { n: x.signups })}</span>
                <span className="w-32 text-right tabular-nums">{both(x.earned)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <SectionTitle icon={MessagesSquare} title="Platform activity (last 30 days)" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Messages" value={num(act.messages_30d.in + act.messages_30d.out)} sub={t("{i} received · {o} sent", { i: num(act.messages_30d.in), o: num(act.messages_30d.out) })} />
        <Tile label="New conversations" value={num(act.conversations_30d)} />
        <Tile label="Orders" value={num(act.orders_30d.count)} sub={act.orders_30d.value.NPR ? t("{amount} in order value", { amount: npr(act.orders_30d.value.NPR) }) : undefined} />
        <Tile label="Posts & broadcasts" value={num(act.posts_published_30d)} sub={t("posts published · {n} broadcast messages", { n: num(act.broadcast_messages_30d) })} />
      </div>
      <div className="card p-4">
        <p className="text-sm font-semibold">{t("Connected channels")}</p>
        {act.channels.length === 0 ? <p className="mt-2 text-sm text-slate-500">{t("No channels connected yet.")}</p> : (
          <div className="mt-3 flex flex-wrap gap-2">
            {act.channels.map((c) => (
              <span key={c.provider} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm">
                <ProviderIcon provider={c.provider} size="xs" /> {providerUI(c.provider).label} <b className="tabular-nums">{c.count}</b>
              </span>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default function AdminPanelPage() {
  const { me } = useMe();
  const t = useT();
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [rows, setRows] = useState<PlatformWorkspace[] | null>(null);
  const [count, setCount] = useState(0);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [today] = useState(() => Date.now());
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => { const timer = setTimeout(() => setDebounced(q), 300); return () => clearTimeout(timer); }, [q]);
  const loadRows = useCallback(() => {
    Api.platformWorkspaces({ q: debounced, filter }).then((r) => { setRows(r.results); setCount(r.count); }).catch((e) => setError(e.message));
  }, [debounced, filter]);
  const loadOverview = useCallback(() => { Api.platformOverview().then(setOverview).catch((e) => setError(e.message)); }, []);
  useEffect(() => { loadRows(); }, [loadRows]);
  useEffect(() => { loadOverview(); }, [loadOverview]);

  if (!me.user.is_platform_admin) {
    return <div className="p-8 text-sm text-slate-600">{t("Only OmniInbox platform admins can open this page.")}</div>;
  }

  const days = (() => {
    // last 30 days, including days without sign-ups
    const byDay = new Map((overview?.signups_by_day ?? []).map((d) => [d.day, d.count]));
    return Array.from({ length: 30 }, (_, i) => {
      const d = new Date(today - (29 - i) * 86400000).toISOString().slice(0, 10);
      return { label: new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short" }), value: byDay.get(d) ?? 0 };
    });
  })();
  const months = overview?.revenue_by_month ?? [];

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold"><ShieldCheck size={20} className="text-brand-600" /> {t("Platform admin")}</h1>
            <p className="text-sm text-slate-600">{t("Every workspace on OmniInbox: who's paying, trials, revenue and account status.")}</p>
          </div>
          <div className="flex gap-2">
            <Link href="/admin-panel/affiliates" className="btn-secondary"><Gift size={15} /> {t("Affiliates")}</Link>
            <button className="btn-secondary" onClick={() => { loadOverview(); loadRows(); setRefreshKey((k) => k + 1); }}><RotateCcw size={15} /> {t("Refresh")}</button>
          </div>
        </div>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        {!overview ? <div className="flex justify-center p-10 text-slate-400"><LoaderCircle className="animate-spin" /></div> : (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Tile label="Monthly recurring revenue" value={npr(overview.mrr.NPR)} sub={t("+ {amount} in USD", { amount: usd(overview.mrr.USD) })} />
              <Tile label="Revenue this month" value={npr(overview.revenue.this_month.NPR)}
                sub={t("{usd} · last month {npr}", { usd: usd(overview.revenue.this_month.USD), npr: npr(overview.revenue.last_month.NPR) })} />
              <Tile label="Paying workspaces" value={overview.workspaces.paying} sub={overview.plans.map((p) => `${p.count} ${p.name}`).join(" · ") || t("No paid plans yet")} />
              <Tile label="On free trial" value={overview.workspaces.trial}
                sub={t("{n} ending within 7 days", { n: overview.trials_ending_7d })} tone={overview.trials_ending_7d ? "warn" : undefined} />
              <Tile label="All workspaces" value={overview.workspaces.total} sub={t("{n} user accounts", { n: overview.users })} />
              <Tile label="Expired plans" value={overview.workspaces.expired} sub={t("Fell back to Free")} tone={overview.workspaces.expired ? "warn" : undefined} />
              <Tile label="Suspended" value={overview.workspaces.suspended} tone={overview.workspaces.suspended ? "bad" : undefined} sub={t("Blocked by you")} />
              <Tile label="Revenue all time" value={npr(overview.revenue.all_time.NPR)} sub={t("{amount} in USD", { amount: usd(overview.revenue.all_time.USD) })} />
            </div>
            <div className="grid gap-3 lg:grid-cols-3">
              <Bars title="New workspaces (last 30 days)" points={days} format={(n) => `${n}`} />
              <Bars title="Revenue by month (NPR)" points={months.map((m) => ({ label: m.month, value: Number(m.NPR) }))} format={(n) => npr(String(n))} />
              <Bars title="Revenue by month (USD)" points={months.map((m) => ({ label: m.month, value: Number(m.USD) }))} format={(n) => usd(String(n))} />
            </div>
          </>
        )}

        <Insights key={refreshKey} today={today} />

        <SectionTitle icon={ShieldCheck} title="All workspaces" />

        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-3">
            <div className="flex flex-wrap gap-1">
              {FILTERS.map(([key, label]) => (
                <button key={key} onClick={() => setFilter(key)}
                  className={clsx("rounded-full px-3 py-1 text-xs font-medium", filter === key ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}>{t(label)}</button>
              ))}
            </div>
            <div className="relative ml-auto w-full sm:w-64">
              <Search size={15} className="absolute left-3 top-2.5 text-slate-400" />
              <input className="input py-1.5 pl-8 text-sm" placeholder={t("Workspace or owner email")} value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("Workspace")}</th><th className="px-3 py-2 font-medium">{t("Status")}</th>
                  <th className="px-3 py-2 font-medium">{t("Plan")}</th><th className="px-3 py-2 font-medium">{t("Ends")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("Paid in total")}</th><th className="px-3 py-2 text-right font-medium">{t("Team")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("Channels")}</th><th className="px-3 py-2 font-medium">{t("Last activity")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows === null && <tr><td colSpan={8} className="p-6 text-center text-slate-400"><LoaderCircle className="mx-auto animate-spin" /></td></tr>}
                {rows?.length === 0 && <tr><td colSpan={8} className="p-6 text-center text-slate-500">{t("No workspaces match.")}</td></tr>}
                {rows?.map((w) => (
                  <tr key={w.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(w.id)}>
                    <td className="px-3 py-2.5">
                      <p className="font-medium text-slate-900">{w.name}</p>
                      <p className="text-xs text-slate-500">{w.owner?.email ?? t("no owner")} · {t("joined {date}", { date: date(w.created_at) })}</p>
                    </td>
                    <td className="px-3 py-2.5"><span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_STYLE[w.status])}>{t(STATUS_LABEL[w.status])}</span></td>
                    <td className="px-3 py-2.5">{w.plan_name}{w.status === "paying" && <span className="text-xs text-slate-500"> · {w.billing_cycle}</span>}</td>
                    <td className="px-3 py-2.5 tabular-nums">{date(w.trial_ends_at ?? w.plan_expires_at)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{Number(w.total_paid.NPR) || !Number(w.total_paid.USD) ? npr(w.total_paid.NPR) : ""}{Number(w.total_paid.USD) ? ` ${usd(w.total_paid.USD)}` : ""}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{w.members}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{w.channels}</td>
                    <td className="px-3 py-2.5 text-slate-500">{w.last_activity ? timeAgo(w.last_activity) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows && count > rows.length && <p className="border-t border-slate-100 p-3 text-xs text-slate-500">{t("Showing {shown} of {count}. Search to narrow down.", { shown: rows.length, count })}</p>}
        </div>
      </div>
      {open && <WorkspaceDrawer id={open} onClose={() => setOpen(null)} onChanged={() => { loadRows(); loadOverview(); }} />}
    </div>
  );
}

function WorkspaceDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const t = useT();
  const [d, setD] = useState<PlatformWorkspaceDetail | null>(null);
  const [reason, setReason] = useState("");
  const [daysToAdd, setDaysToAdd] = useState(30);
  const [plan, setPlan] = useState("pro");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { Api.platformWorkspace(id).then(setD).catch((e) => setMsg(e.message)); }, [id]);

  async function act(body: Parameters<typeof Api.platformAction>[1], done: string) {
    setBusy(true); setMsg("");
    try { setD(await Api.platformAction(id, body)); setMsg(done); setReason(""); onChanged(); }
    catch (e) { setMsg(e instanceof Error ? e.message : t("Failed")); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30" onClick={onClose}>
      <aside className="scroll-thin h-full w-full max-w-lg overflow-y-auto bg-white p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">{d?.name ?? "…"}</h2>
            {d && <span className={clsx("mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium", STATUS_STYLE[d.status])}>{t(STATUS_LABEL[d.status])}</span>}
          </div>
          <button onClick={onClose} className="btn-ghost px-2" aria-label={t("Close")}><X size={18} /></button>
        </div>
        {!d ? <div className="flex justify-center p-10 text-slate-400"><LoaderCircle className="animate-spin" /></div> : (
          <div className="mt-5 space-y-6 text-sm">
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">{t("Plan")}</p><p className="font-semibold capitalize">{d.plan}</p></div>
              <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">{t("Conversations")}</p><p className="font-semibold tabular-nums">{d.usage.conversations}</p></div>
              <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">{t("Messages (30 days)")}</p><p className="font-semibold tabular-nums">{d.usage.messages_30d}</p></div>
            </div>
            <p className="text-slate-600">{t("Plan ends:")} <b>{date(d.plan_expires_at)}</b></p>

            <section>
              <h3 className="font-semibold">{t("Team")}</h3>
              <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {d.members.map((m) => (
                  <li key={m.email} className="flex items-center justify-between gap-2 px-3 py-2">
                    <span className="min-w-0"><span className="block truncate font-medium">{m.name}</span><span className="block truncate text-xs text-slate-500">{m.email}</span></span>
                    <span className="shrink-0 text-xs text-slate-500">{t(m.role.charAt(0).toUpperCase() + m.role.slice(1))} · {m.last_login ? t("seen {time}", { time: timeAgo(m.last_login) }) : t("never logged in")}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <h3 className="font-semibold">{t("Payments")}</h3>
              {d.payments.length === 0 ? <p className="mt-1 text-slate-500">{t("No payments yet.")}</p> : (
                <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {d.payments.map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-2 px-3 py-2">
                      <span>{p.currency === "NPR" ? npr(p.amount) : usd(p.amount)} <span className="text-xs text-slate-500">· {p.plan} {p.cycle} · {p.gateway}</span></span>
                      <span className={clsx("text-xs", p.status === "paid" ? "text-emerald-700" : p.status === "failed" ? "text-red-600" : "text-slate-500")}>{t(p.status.charAt(0).toUpperCase() + p.status.slice(1))} · {date(p.paid_at ?? p.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="space-y-3 rounded-lg border border-slate-200 p-3">
              <h3 className="font-semibold">{t("Extend or change plan")}</h3>
              <p className="text-xs text-slate-500">{t("For payments received outside the app (bank transfer, cash) or to give extra time.")}</p>
              <div className="flex flex-wrap gap-2">
                <select className="input w-32 py-1.5" value={plan} onChange={(e) => setPlan(e.target.value)}>
                  {["starter", "pro", "business", "enterprise"].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
                </select>
                <select className="input w-28 py-1.5" value={daysToAdd} onChange={(e) => setDaysToAdd(Number(e.target.value))}>
                  {[7, 14, 30, 90, 365].map((n) => <option key={n} value={n}>{t("+{n} days", { n })}</option>)}
                </select>
                <button className="btn-secondary" disabled={busy} onClick={() => act({ action: "extend", days: daysToAdd, plan }, t("Extended by {n} days.", { n: daysToAdd }))}>
                  <CalendarPlus size={15} /> {t("Extend")}
                </button>
              </div>
            </section>

            <section className={clsx("space-y-3 rounded-lg border p-3", d.status === "suspended" ? "border-red-200 bg-red-50" : "border-slate-200")}>
              <h3 className="font-semibold">{d.status === "suspended" ? t("Suspended") : t("Suspend workspace")}</h3>
              {d.status === "suspended" ? (
                <>
                  <p className="text-red-800">{t("Reason shown to the team: “{reason}”", { reason: d.suspended_reason })}</p>
                  <button className="btn-secondary" disabled={busy} onClick={() => act({ action: "unsuspend" }, t("Workspace reactivated."))}><RotateCcw size={15} /> {t("Reactivate")}</button>
                </>
              ) : (
                <>
                  <p className="text-xs text-slate-500">{t("The team can't use the app, and their channels, website chat and payment links stop until you reactivate it. Nothing is deleted.")}</p>
                  <input className="input" placeholder={t("Reason (the team sees this)")} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
                  <button className="btn bg-red-600 text-white hover:bg-red-700" disabled={busy || !reason.trim()}
                    onClick={() => act({ action: "suspend", reason: reason.trim() }, t("Workspace suspended."))}><Ban size={15} /> {t("Suspend")}</button>
                </>
              )}
            </section>
            {msg && <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm">{msg}</p>}
          </div>
        )}
      </aside>
    </div>
  );
}
