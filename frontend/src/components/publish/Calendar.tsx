"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, LoaderCircle } from "lucide-react";
import { Api } from "@/lib/api";
import type { SocialPost } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { POST_STATUS } from "./PostsList";
import { useT } from "@/lib/i18n";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

export default function Calendar({ refreshKey, onOpen }: { refreshKey: number; onOpen: (p: SocialPost) => void }) {
  const t = useT();
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [posts, setPosts] = useState<SocialPost[] | null>(null);

  const cells = useMemo(() => {
    const first = new Date(month);
    first.setDate(1 - ((month.getDay() + 6) % 7)); // back to Monday
    return Array.from({ length: 42 }, (_, i) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + i));
  }, [month]);

  useEffect(() => {
    let live = true;
    setPosts(null);
    const end = new Date(cells[41]); end.setDate(end.getDate() + 1);
    Api.posts({ from: cells[0].toISOString(), to: end.toISOString() }).then((p) => live && setPosts(p)).catch(() => live && setPosts([]));
    return () => { live = false; };
  }, [cells, refreshKey]);

  const byDay = useMemo(() => {
    const map = new Map<string, SocialPost[]>();
    for (const p of posts ?? []) {
      const when = p.status === "scheduled" ? p.scheduled_at : (p.published_at ?? p.scheduled_at);
      if (!when) continue;
      const k = dayKey(new Date(when));
      map.set(k, [...(map.get(k) ?? []), p]);
    }
    return map;
  }, [posts]);

  const today = dayKey(new Date());
  const shift = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1));

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <p className="font-semibold">{month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</p>
        <div className="flex items-center gap-1">
          {posts === null && <LoaderCircle className="mr-2 animate-spin text-slate-400" size={16} />}
          <button type="button" className="btn-ghost px-2" onClick={() => shift(-1)} aria-label={t("Previous month")}><ChevronLeft size={18} /></button>
          <button type="button" className="btn-ghost px-3 text-xs" onClick={() => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }}>{t("Today")}</button>
          <button type="button" className="btn-ghost px-2" onClick={() => shift(1)} aria-label={t("Next month")}><ChevronRight size={18} /></button>
        </div>
      </div>
      <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50 text-center text-[11px] font-medium uppercase text-slate-500">
        {DAYS.map((d) => <div key={d} className="py-1.5">{t(d)}</div>)}
      </div>
      <div className="grid grid-cols-7">
        {cells.map((d) => {
          const items = byDay.get(dayKey(d)) ?? [];
          return (
            <div key={d.toISOString()} className={clsx("min-h-[96px] border-b border-r border-slate-100 p-1",
              d.getMonth() !== month.getMonth() && "bg-slate-50/60 text-slate-400")}>
              <p className={clsx("mb-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[11px]",
                dayKey(d) === today && "bg-brand-600 font-semibold text-white")}>{d.getDate()}</p>
              <div className="space-y-1">
                {items.slice(0, 3).map((p) => {
                  const when = new Date((p.status === "scheduled" ? p.scheduled_at : p.published_at ?? p.scheduled_at)!);
                  return (
                    <button key={p.id} type="button" onClick={() => onOpen(p)} title={p.caption}
                      className={clsx("flex w-full items-center gap-1 truncate rounded px-1 py-0.5 text-left text-[11px]", POST_STATUS[p.status].cls)}>
                      <span className="flex shrink-0 -space-x-1">
                        {p.targets.slice(0, 3).map((x) => <ProviderIcon key={x.account.id} provider={x.account.platform} size="xs" className="rounded-full ring-1 ring-white" />)}
                      </span>
                      <span className="shrink-0 font-medium">{when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
                      <span className="truncate">{p.caption}</span>
                    </button>
                  );
                })}
                {items.length > 3 && <p className="px-1 text-[10px] text-slate-500">{t("+{n} more", { n: items.length - 3 })}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
