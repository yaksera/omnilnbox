"use client";

import { useRef, useState } from "react";
import clsx from "clsx";
import {
  ArrowDown, Check, CircleAlert, Hand, LoaderCircle, MessageCircle, MessagesSquare, RefreshCw, Search, SlidersHorizontal,
  UserCheck, UserMinus, X,
} from "lucide-react";
import type { Conversation, Me, Stats, Tag } from "@/lib/types";
import AIReportCard from "@/components/ai/AIReportCard";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { avatarColor, initials, timeAgo } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { BottomSheet } from "@/components/mobile/MobileNav";

export type MobileFilter = { kind: "all" } | { kind: "unread" } | { kind: "handoff" } | { kind: "mine" }
  | { kind: "provider"; provider: string } | { kind: "tag"; tag: number };

const STATUS = [["open", "Open"], ["pending", "Pending"], ["closed", "Done"], ["all", "All"]] as const;

const CATEGORY: Record<string, [string, string]> = {
  order: ["Order", "bg-emerald-50 text-emerald-700"], lead: ["Lead", "bg-sky-50 text-sky-700"],
  complaint: ["Complaint", "bg-red-50 text-red-700"], question: ["Question", "bg-violet-50 text-violet-700"],
};

function Avatar({ name, url }: { name: string; url?: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className="h-12 w-12 shrink-0 rounded-full object-cover" />;
  }
  return (
    <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white" style={{ background: avatarColor(name) }}>
      {initials(name)}
    </span>
  );
}

const ACTION_W = 76;

/** A row you can swipe left to reveal quick actions (like a phone's mail app). */
function SwipeRow({ children, actions, onTap }: {
  children: React.ReactNode; onTap: () => void;
  actions: Array<{ label: string; icon: React.ReactNode; className: string; onClick: () => void }>;
}) {
  const [x, setX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const start = useRef<{ x: number; y: number; base: number; locked: "h" | "v" | null } | null>(null);
  const max = actions.length * ACTION_W;
  return (
    <div className="relative overflow-hidden bg-white">
      <div className="absolute inset-y-0 right-0 flex">
        {actions.map((a) => (
          <button key={a.label} onClick={() => { setX(0); a.onClick(); }} style={{ width: ACTION_W }}
            className={clsx("flex flex-col items-center justify-center gap-1 text-xs font-semibold text-white", a.className)}>
            {a.icon}{a.label}
          </button>
        ))}
      </div>
      <div className={clsx("relative bg-white", !dragging && "transition-transform duration-200")} style={{ transform: `translateX(${x}px)` }}
        onTouchStart={(e) => { start.current = { x: e.touches[0].clientX, y: e.touches[0].clientY, base: x, locked: null }; }}
        onTouchMove={(e) => {
          const s = start.current;
          if (!s) return;
          const dx = e.touches[0].clientX - s.x, dy = e.touches[0].clientY - s.y;
          if (!s.locked && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) s.locked = Math.abs(dx) > Math.abs(dy) ? "h" : "v";
          if (s.locked !== "h") return;
          setDragging(true);
          setX(Math.max(-max - 24, Math.min(0, s.base + dx)));
        }}
        onTouchEnd={() => {
          setDragging(false);
          if (start.current?.locked === "h") setX(x < -max / 2 ? -max : 0);
          start.current = null;
        }}
        onClick={() => { if (x !== 0) setX(0); else onTap(); }}>
        {children}
      </div>
    </div>
  );
}

export default function MobileConversationList({
  me, conversations, stats, providers, tags, now, tab, setTab, filter, setFilter, status, setStatus, query, setQuery,
  onOpen, onRefresh, onUpdate,
}: {
  me: Me; conversations: Conversation[] | null; stats: Stats | null; providers: string[]; tags: Tag[]; now: number;
  tab: "message" | "comment"; setTab: (t: "message" | "comment") => void;
  filter: MobileFilter; setFilter: (f: MobileFilter) => void;
  status: string; setStatus: (s: string) => void; query: string; setQuery: (q: string) => void;
  onOpen: (id: string) => void; onRefresh: () => Promise<void>;
  onUpdate: (c: Conversation, body: { status?: string; assigned_to_id?: number | null }) => void;
}) {
  const t = useT();
  const [searching, setSearching] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const pullStart = useRef<number | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const isF = (f: MobileFilter) => JSON.stringify(f) === JSON.stringify(filter);
  const unreadBy = stats?.unread_by_kind;
  const chip = (f: MobileFilter, label: React.ReactNode, count?: number, tone?: "warn") => (
    <button key={JSON.stringify(f)} onClick={() => setFilter(isF(f) && f.kind !== "all" ? { kind: "all" } : f)}
      className={clsx("flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition",
        isF(f) ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-700 active:bg-slate-100")}>
      {label}
      {!!count && <span className={clsx("rounded-full px-1.5 text-[11px] font-bold",
        isF(f) ? "bg-white/20 text-white" : tone === "warn" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600")}>{count}</span>}
    </button>
  );

  async function refresh() {
    setRefreshing(true);
    try { await onRefresh(); } finally { setRefreshing(false); setPull(0); }
  }

  const statusLabel = STATUS.find(([k]) => k === status)?.[1] ?? "Open";

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-white md:hidden">
      {/* Header */}
      <div className="bg-gradient-to-b from-brand-50/70 to-white px-4 pb-2 pt-3">
        {searching ? (
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input autoFocus className="w-full rounded-full border border-slate-200 bg-white py-2.5 pl-10 pr-3 outline-none focus:border-brand-500"
                placeholder={t("Search name, handle, message…")} value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <button className="px-1 text-sm font-medium text-brand-700" onClick={() => { setQuery(""); setSearching(false); }}>{t("Cancel")}</button>
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <div className="min-w-0 flex-1">
              <h1 className="text-[28px] font-bold leading-tight tracking-tight">{t("Inbox")}</h1>
              <p className="truncate text-xs text-slate-500">{me.workspace.name}</p>
            </div>
            <button className="relative rounded-full p-2.5 text-slate-700 active:bg-slate-100" onClick={() => setFiltersOpen(true)} aria-label={t("Filters")}>
              <SlidersHorizontal size={22} />
              {status !== "open" && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-brand-600" />}
            </button>
            <button className="rounded-full p-2.5 text-slate-700 active:bg-slate-100" onClick={() => setSearching(true)} aria-label={t("Search")}><Search size={22} /></button>
          </div>
        )}

        {/* Messages / Comments */}
        <div className="mt-3 grid grid-cols-2 rounded-2xl bg-slate-100 p-1">
          {([["message", "Messages", MessageCircle, unreadBy?.message], ["comment", "Comments", MessagesSquare, unreadBy?.comment]] as const).map(([k, label, Icon, n]) => (
            <button key={k} onClick={() => setTab(k)}
              className={clsx("flex items-center justify-center gap-2 rounded-xl py-2 text-[15px] font-semibold transition",
                tab === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500")}>
              <Icon size={17} /> {t(label)}
              {!!n && <span className={clsx("rounded-full px-1.5 text-xs font-bold", tab === k ? "bg-brand-600 text-white" : "bg-slate-200 text-slate-600")}>{n}</span>}
            </button>
          ))}
        </div>
      </div>

      {/* Quick filters */}
      <div className="no-scrollbar flex gap-2 overflow-x-auto border-b border-slate-100 px-4 pb-3 pt-1">
        {chip({ kind: "all" }, t("All"))}
        {chip({ kind: "unread" }, <><CircleAlert size={15} /> {t("Unread")}</>, stats?.unread_conversations)}
        {!!stats?.ai_handoff && chip({ kind: "handoff" }, <><Hand size={15} /> {t("Needs you")}</>, stats.ai_handoff, "warn")}
        {chip({ kind: "mine" }, <><UserCheck size={15} /> {t("Mine")}</>, stats?.assigned_to_me)}
        {providers.map((p) => chip({ kind: "provider", provider: p }, <><ProviderIcon provider={p} size="xs" /> {providerUI(p).label}</>, stats?.by_provider[p]?.unread))}
        {tags.map((tg) => chip({ kind: "tag", tag: tg.id }, <><span className="h-2.5 w-2.5 rounded-full" style={{ background: tg.color }} /> {tg.name}</>))}
      </div>
      {status !== "open" && (
        <div className="flex items-center justify-between bg-slate-50 px-4 py-1.5 text-xs text-slate-600">
          {t("Showing: {status}", { status: t(statusLabel) })}
          <button className="font-semibold text-brand-700" onClick={() => setStatus("open")}>{t("Show open")}</button>
        </div>
      )}

      {/* List with pull-to-refresh */}
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
        onTouchStart={(e) => { pullStart.current = scroller.current?.scrollTop === 0 ? e.touches[0].clientY : null; }}
        onTouchMove={(e) => { if (pullStart.current !== null && !refreshing) setPull(Math.max(0, Math.min(90, (e.touches[0].clientY - pullStart.current) * 0.5))); }}
        onTouchEnd={() => { pullStart.current = null; if (pull > 60) refresh(); else setPull(0); }}>
        <div className="flex items-center justify-center overflow-hidden text-slate-400 transition-[height]" style={{ height: refreshing ? 48 : pull }}>
          {refreshing ? <LoaderCircle className="animate-spin" size={20} /> : <ArrowDown size={20} className={clsx("transition", pull > 60 && "rotate-180 text-brand-600")} />}
        </div>

        {me.workspace.features.includes("ai_chatbot") && <AIReportCard compact />}
        {conversations === null && <div className="flex justify-center p-10 text-slate-400"><LoaderCircle className="animate-spin" /></div>}
        {conversations?.length === 0 && (
          <div className="flex flex-col items-center px-8 py-16 text-center">
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"><Check size={30} /></span>
            <p className="mt-4 font-semibold">{tab === "comment" ? t("No comments here") : t("You're all caught up")}</p>
            <p className="mt-1 text-sm text-slate-500">
              {filter.kind !== "all" || query ? t("Nothing matches this filter.") : tab === "comment"
                ? t("Comments on your Facebook and Instagram posts appear here.") : t("New messages from every channel appear here.")}
            </p>
            {(filter.kind !== "all" || query) && <button className="mt-4 text-sm font-semibold text-brand-700" onClick={() => { setFilter({ kind: "all" }); setQuery(""); }}>{t("Clear filters")}</button>}
          </div>
        )}

        {conversations?.map((c) => {
          const name = c.contact.name || c.contact.handle || t("Unknown");
          const unread = c.unread_count > 0;
          const waitMin = unread && c.status !== "closed" && c.last_message_at ? (now - new Date(c.last_message_at).getTime()) / 60000 : 0;
          const overdue = me.workspace.sla_minutes > 0 && waitMin > me.workspace.sla_minutes;
          const handoff = !!c.ai?.bot_paused && c.ai.pause_reason === "handoff" && c.status !== "closed";
          const cat = c.ai?.category ? CATEGORY[c.ai.category] : undefined;
          const mine = c.assigned_to?.id === me.user.id;
          const actions = [
            c.status === "closed"
              ? { label: t("Reopen"), icon: <RefreshCw size={20} />, className: "bg-slate-500", onClick: () => onUpdate(c, { status: "open" }) }
              : { label: t("Done"), icon: <Check size={20} />, className: "bg-emerald-600", onClick: () => onUpdate(c, { status: "closed" }) },
            mine
              ? { label: t("Release"), icon: <UserMinus size={20} />, className: "bg-slate-400", onClick: () => onUpdate(c, { assigned_to_id: null }) }
              : { label: t("Take"), icon: <UserCheck size={20} />, className: "bg-brand-600", onClick: () => onUpdate(c, { assigned_to_id: me.user.id }) },
          ];
          return (
            <SwipeRow key={c.id} actions={actions} onTap={() => onOpen(c.id)}>
              <div className="flex gap-3 px-4 py-3 active:bg-slate-50">
                <div className="relative h-12 shrink-0 self-start">
                  <Avatar name={name} url={c.contact.avatar_url} />
                  <ProviderIcon provider={c.channel.provider} size="xs" className="absolute -bottom-0.5 -right-0.5 ring-2 ring-white" />
                </div>
                <div className="min-w-0 flex-1 border-b border-slate-100 pb-3">
                  <div className="flex items-baseline gap-2">
                    <span className={clsx("min-w-0 flex-1 truncate text-[15px]", unread ? "font-bold text-slate-900" : "font-medium text-slate-800")}>{name}</span>
                    <span className={clsx("shrink-0 text-xs", overdue ? "font-semibold text-red-600" : unread ? "font-semibold text-brand-700" : "text-slate-400")}>
                      {overdue && "⏱ "}{timeAgo(c.last_message_at)}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <p className={clsx("min-w-0 flex-1 truncate text-sm", unread ? "font-medium text-slate-800" : "text-slate-500")}>
                      {c.last_direction === "out" && <span className="text-slate-400">{t("You:")} </span>}
                      {c.subject && c.kind !== "comment" ? `${c.subject} · ` : ""}{c.last_message_preview}
                    </p>
                    {unread && <span className="min-w-[20px] rounded-full bg-brand-600 px-1.5 text-center text-[11px] font-bold leading-5 text-white">{c.unread_count}</span>}
                  </div>
                  {(handoff || cat || c.tags.length > 0 || c.assigned_to || c.status !== "open") && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      {handoff && <span className="flex items-center gap-1 rounded-md bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800"><Hand size={11} /> {t("Needs you")}</span>}
                      {cat && <span className={clsx("rounded-md px-1.5 py-0.5 text-[11px] font-semibold", cat[1])}>{t(cat[0])}</span>}
                      {c.status === "pending" && <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{t("Pending")}</span>}
                      {c.status === "closed" && <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{t("Done")}</span>}
                      {c.tags.slice(0, 2).map((tg) => (
                        <span key={tg.id} className="rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-white" style={{ background: tg.color }}>{tg.name}</span>
                      ))}
                      {c.tags.length > 2 && <span className="text-[11px] text-slate-400">+{c.tags.length - 2}</span>}
                      {c.assigned_to && (
                        <span className="ml-auto flex items-center gap-1 text-[11px] text-slate-500">
                          <span className="flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-bold text-white" style={{ background: avatarColor(c.assigned_to.email) }}>{initials(c.assigned_to.name)}</span>
                          {mine ? t("You") : c.assigned_to.name.split(" ")[0]}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </SwipeRow>
          );
        })}
        {!!conversations?.length && <p className="py-6 text-center text-xs text-slate-400">{t("Swipe left on a chat for quick actions")}</p>}
      </div>

      <BottomSheet open={filtersOpen} onClose={() => setFiltersOpen(false)} title={t("Show conversations")}>
        <div className="space-y-2">
          {STATUS.map(([k, label]) => (
            <button key={k} onClick={() => { setStatus(k); setFiltersOpen(false); }}
              className={clsx("flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left font-medium",
                status === k ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-200 active:bg-slate-50")}>
              {t(label)} {status === k && <Check size={18} />}
            </button>
          ))}
        </div>
        {(filter.kind !== "all" || status !== "open") && (
          <button className="mt-4 flex w-full items-center justify-center gap-1 text-sm font-semibold text-brand-700"
            onClick={() => { setFilter({ kind: "all" }); setStatus("open"); setFiltersOpen(false); }}><X size={15} /> {t("Reset filters")}</button>
        )}
      </BottomSheet>
    </div>
  );
}
