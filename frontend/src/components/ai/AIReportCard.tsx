"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CalendarCheck, Mic, MessageCircle, Receipt, ShoppingBag, Sparkles, BellRing, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Api } from "@/lib/api";
import type { AIReport } from "@/lib/types";
import { useT } from "@/lib/i18n";

const SEEN = "omni.aiReportSeen";

function readSeen() {
  try { return Number(window.localStorage.getItem(SEEN) || 0); } catch { return 0; }
}
function writeSeen() {
  try { window.localStorage.setItem(SEEN, String(Date.now())); } catch { /* storage unavailable */ }
}

/** "While you were away": what the AI staff did. `compact` = a dismissible banner (inbox); otherwise a card. */
export default function AIReportCard({ compact = false, hours: fixedHours }: { compact?: boolean; hours?: number }) {
  const t = useT();
  const [r, setR] = useState<AIReport | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let hours = fixedHours ?? 24;
    if (compact) {
      const seen = readSeen();
      // since the last time this banner was closed, between 1 hour and 3 days
      if (seen) hours = Math.min(72, Math.max(1, Math.ceil((Date.now() - seen) / 3_600_000)));
      if (seen && Date.now() - seen < 3_600_000) { setHidden(true); return; }
    }
    Api.aiReport(hours).then(setR).catch(() => undefined);
  }, [compact, fixedHours]);

  if (hidden || !r) return null;
  const items: Array<[LucideIcon, number, string, string?]> = [
    [ShoppingBag, r.orders, r.orders === 1 ? "order taken" : "orders taken", "/orders"],
    [CalendarCheck, r.visits, r.visits === 1 ? "visit booked" : "visits booked", "/visits"],
    [MessageCircle, r.conversations_answered, r.conversations_answered === 1 ? "chat answered" : "chats answered"],
    [Mic, r.voice_notes, r.voice_notes === 1 ? "voice note understood" : "voice notes understood"],
    [Receipt, r.payments_to_confirm, r.payments_to_confirm === 1 ? "payment to confirm" : "payments to confirm", "/inbox"],
    [BellRing, r.followups, r.followups === 1 ? "follow-up sent" : "follow-ups sent"],
  ];
  const busy = items.some(([, n]) => n > 0);
  if (compact && !busy) return null;

  if (compact) {
    return (
      <div className="relative m-2 rounded-2xl bg-gradient-to-br from-brand-600 to-indigo-600 p-3 pr-9 text-white shadow-sm">
        <button type="button" onClick={() => { writeSeen(); setHidden(true); }} className="absolute right-2 top-2 rounded-full p-1 text-white/80 hover:bg-white/10" aria-label={t("Close")}><X size={16} /></button>
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-white/80"><Sparkles size={14} /> {t("While you were away")}</p>
        <p className="mt-1 text-sm">
          {items.filter(([, n]) => n > 0).map(([, n, label]) => `${n} ${t(label)}`).join(" · ")}
        </p>
        {r.orders > 0 && <p className="mt-0.5 text-xs text-white/80">{t("Orders worth Rs {amount}", { amount: Math.round(Number(r.orders_total)).toLocaleString() })}</p>}
      </div>
    );
  }

  return (
    <div className="card p-4">
      <p className="flex items-center gap-1.5 text-sm font-semibold"><Sparkles size={16} className="text-brand-600" /> {t("Your AI staff, last 24 hours")}</p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {items.map(([Icon, n, label, href]) => {
          const body = (
            <>
              <Icon size={16} className="text-brand-600" />
              <span className="text-lg font-bold leading-none">{n}</span>
              <span className="text-[11px] leading-tight text-slate-500">{t(label)}</span>
            </>
          );
          return href ? (
            <Link key={label} href={href} className="flex flex-col gap-1 rounded-xl bg-slate-50 p-2.5 hover:bg-slate-100">{body}</Link>
          ) : <div key={label} className="flex flex-col gap-1 rounded-xl bg-slate-50 p-2.5">{body}</div>;
        })}
      </div>
      {r.upcoming_visits > 0 && <Link href="/visits" className="mt-3 block text-xs font-medium text-brand-700 hover:underline">{t(r.upcoming_visits === 1 ? "1 visit in the next 24 hours →" : "{n} visits in the next 24 hours →", { n: r.upcoming_visits })}</Link>}
    </div>
  );
}
