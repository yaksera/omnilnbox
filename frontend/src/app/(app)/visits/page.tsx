"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Bot, CalendarCheck, CalendarClock, Check, LoaderCircle, MessageCircle, Phone, Plus, Trash2, UserX, X } from "lucide-react";
import { Api } from "@/lib/api";
import type { Booking, BookingStatus } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { useLiveUpdates } from "@/lib/realtime";
import { useT } from "@/lib/i18n";

const STATUS: Record<BookingStatus, string> = {
  booked: "bg-sky-50 text-sky-700", confirmed: "bg-indigo-50 text-indigo-700", done: "bg-emerald-50 text-emerald-700",
  no_show: "bg-amber-50 text-amber-800", cancelled: "bg-slate-100 text-slate-500",
};
type Range = "upcoming" | "past";

function dayKey(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}
/** yyyy-MM-ddTHH:mm in the browser's time zone, for <input type="datetime-local"> */
function localInput(d: Date) {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function VisitsPage() {
  const t = useT();
  const [range, setRange] = useState<Range>("upcoming");
  const [rows, setRows] = useState<Booking[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [moving, setMoving] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    const now = new Date();
    const params = range === "upcoming"
      ? { from: new Date(now.getTime() - 2 * 3_600_000).toISOString(), to: new Date(now.getTime() + 60 * 86_400_000).toISOString() }
      : { from: new Date(now.getTime() - 60 * 86_400_000).toISOString(), to: now.toISOString() };
    return Api.bookings(params).then((r) => setRows(range === "past" ? r.reverse() : r)).catch((e) => setError(e instanceof Error ? e.message : t("Couldn't load")));
  }, [range, t]);
  useEffect(() => { setRows(null); load(); }, [load]);
  useLiveUpdates(() => { load(); });

  const groups = useMemo(() => {
    const out: Array<{ key: string; label: string; items: Booking[] }> = [];
    const today = new Date();
    const tomorrow = new Date(today.getTime() + 86_400_000);
    for (const b of rows ?? []) {
      const d = new Date(b.starts_at);
      const key = dayKey(d);
      let g = out.find((x) => x.key === key);
      if (!g) {
        const label = key === dayKey(today) ? t("Today") : key === dayKey(tomorrow) ? t("Tomorrow")
          : d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
        g = { key, label, items: [] };
        out.push(g);
      }
      g.items.push(b);
    }
    return out;
  }, [rows, t]);

  async function update(b: Booking, body: Parameters<typeof Api.updateBooking>[1]) {
    setError("");
    try {
      const next = await Api.updateBooking(b.id, body);
      setRows((rs) => rs?.map((x) => (x.id === b.id ? next : x)) ?? rs);
    } catch (err) { setError(err instanceof Error ? err.message : t("Failed")); }
  }

  const todayCount = rows?.filter((b) => dayKey(new Date(b.starts_at)) === dayKey(new Date()) && ["booked", "confirmed"].includes(b.status)).length ?? 0;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="flex items-center gap-2 text-xl font-bold"><CalendarCheck size={22} /> {t("Visits & appointments")}</h1>
            <p className="text-sm text-slate-500">{t("Counselling sessions, campus visits and appointments, booked by your team or by the AI in chat.")}</p>
          </div>
          <button type="button" className="btn-primary" onClick={() => setAdding(true)}><Plus size={16} /> {t("Add visit")}</button>
        </div>

        <div className="mt-4 flex items-center gap-2">
          {(["upcoming", "past"] as const).map((r) => (
            <button key={r} type="button" onClick={() => setRange(r)}
              className={clsx("rounded-full px-3 py-1 text-sm font-medium", range === r ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600")}>
              {t(r === "upcoming" ? "Upcoming" : "Past")}</button>
          ))}
          {range === "upcoming" && todayCount > 0 && <span className="text-sm text-slate-500">{t("{n} today", { n: todayCount })}</span>}
          <Link href="/automations#sales" className="ml-auto text-xs text-brand-700 hover:underline">{t("AI booking settings")}</Link>
        </div>

        {error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {adding && <AddVisit onClose={() => setAdding(false)} onAdded={(b) => { setAdding(false); setRows((rs) => [...(rs ?? []), b].sort((a, c) => a.starts_at.localeCompare(c.starts_at))); }} />}

        {rows === null ? <div className="flex justify-center p-10 text-slate-400"><LoaderCircle className="animate-spin" /></div>
          : rows.length === 0 ? (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 p-10 text-center">
              <CalendarClock className="mx-auto text-slate-300" size={40} />
              <p className="mt-3 font-semibold">{range === "upcoming" ? t("No upcoming visits") : t("No past visits")}</p>
              <p className="mt-1 text-sm text-slate-500">{t("Turn on “Book visits” in AI → Sales staff and the AI books them from chat, inside your business hours.")}</p>
            </div>
          ) : (
            <div className="mt-5 space-y-6">
              {groups.map((g) => (
                <section key={g.key}>
                  <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{g.label}</h2>
                  <div className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white">
                    {g.items.map((b) => {
                      const d = new Date(b.starts_at);
                      const active = b.status === "booked" || b.status === "confirmed";
                      return (
                        <div key={b.id} className={clsx("flex gap-3 p-3 sm:p-4", !active && "opacity-70")}>
                          <div className="w-[4.75rem] shrink-0 text-center">
                            <p className="whitespace-nowrap text-sm font-bold sm:text-base">{d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</p>
                            <p className="text-[11px] text-slate-500">{b.minutes} {t("min")}</p>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="flex flex-wrap items-center gap-1.5 font-semibold">
                              {b.name || t("Unnamed")}
                              {b.source === "ai" && <span className="inline-flex items-center gap-0.5 rounded-full bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-700"><Bot size={10} /> {t("Booked by AI")}</span>}
                              <span className={clsx("rounded-full px-1.5 py-0.5 text-[10px] font-medium", STATUS[b.status])}>{t(b.status_label)}</span>
                            </p>
                            {b.purpose && <p className="text-sm text-slate-600">{b.purpose}</p>}
                            <p className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                              {b.phone && <a href={`tel:${b.phone}`} className="inline-flex items-center gap-1 hover:text-brand-700"><Phone size={12} /> {b.phone}</a>}
                              {b.conversation_id && (
                                <Link href={`/inbox?c=${b.conversation_id}`} className="inline-flex items-center gap-1 hover:text-brand-700">
                                  {b.provider ? <ProviderIcon provider={b.provider} size="sm" /> : <MessageCircle size={12} />} {t("Open chat")}
                                </Link>
                              )}
                            </p>
                            {moving === b.id ? (
                              <MoveForm booking={b} onCancel={() => setMoving(null)} onSave={async (iso, notify) => { await update(b, { starts_at: iso, notify }); setMoving(null); }} />
                            ) : (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {active && <button type="button" className="chip-btn" onClick={() => update(b, { status: "done" })}><Check size={13} /> {t("Visited")}</button>}
                                {active && <button type="button" className="chip-btn" onClick={() => update(b, { status: "no_show" })}><UserX size={13} /> {t("Didn't come")}</button>}
                                {active && <button type="button" className="chip-btn" onClick={() => setMoving(b.id)}><CalendarClock size={13} /> {t("Change time")}</button>}
                                {active && <button type="button" className="chip-btn" onClick={() => update(b, { status: "cancelled", notify: !!b.conversation_id })}><X size={13} /> {t("Cancel")}</button>}
                                {!active && <button type="button" className="chip-btn" onClick={() => update(b, { status: "booked" })}>{t("Undo")}</button>}
                                {!active && (
                                  <button type="button" className="chip-btn text-red-600" aria-label={t("Delete")}
                                    onClick={async () => { await Api.deleteBooking(b.id); setRows((rs) => rs?.filter((x) => x.id !== b.id) ?? rs); }}><Trash2 size={13} /></button>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}
      </div>
    </div>
  );
}

function MoveForm({ booking, onSave, onCancel }: { booking: Booking; onSave: (iso: string, notify: boolean) => Promise<void>; onCancel: () => void }) {
  const t = useT();
  const [value, setValue] = useState(localInput(new Date(booking.starts_at)));
  const [notify, setNotify] = useState(!!booking.conversation_id);
  const [busy, setBusy] = useState(false);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input type="datetime-local" className="input w-auto py-1 text-sm" value={value} onChange={(e) => setValue(e.target.value)} />
      {booking.conversation_id && <label className="flex items-center gap-1 text-xs"><input type="checkbox" className="accent-brand-600" checked={notify} onChange={(e) => setNotify(e.target.checked)} /> {t("Tell the customer")}</label>}
      <button type="button" className="btn-primary py-1 text-xs" disabled={busy || !value}
        onClick={async () => { setBusy(true); try { await onSave(new Date(value).toISOString(), notify); } finally { setBusy(false); } }}>{t("Save")}</button>
      <button type="button" className="btn-ghost py-1 text-xs" onClick={onCancel}>{t("Cancel")}</button>
    </div>
  );
}

function AddVisit({ onClose, onAdded }: { onClose: () => void; onAdded: (b: Booking) => void }) {
  const t = useT();
  const [form, setForm] = useState(() => ({ name: "", phone: "", purpose: "", when: localInput(new Date(Date.now() + 86_400_000)), minutes: 30 }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      onAdded(await Api.createBooking({ name: form.name, phone: form.phone, purpose: form.purpose, minutes: form.minutes, starts_at: new Date(form.when).toISOString() }));
    } catch (err) { setError(err instanceof Error ? err.message : t("Couldn't save")); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className="card mt-4 grid gap-3 p-4 sm:grid-cols-2">
      <label className="text-sm">{t("Name")}<input className="input mt-1" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
      <label className="text-sm">{t("Phone")}<input className="input mt-1" inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
      <label className="text-sm sm:col-span-2">{t("What it's about")}<input className="input mt-1" value={form.purpose} placeholder={t("e.g. IELTS + Australia, Feb intake")} onChange={(e) => setForm({ ...form, purpose: e.target.value })} /></label>
      <label className="text-sm">{t("Date and time")}<input type="datetime-local" className="input mt-1" required value={form.when} onChange={(e) => setForm({ ...form, when: e.target.value })} /></label>
      <label className="text-sm">{t("Length (minutes)")}<input type="number" min={5} max={480} className="input mt-1" value={form.minutes} onChange={(e) => setForm({ ...form, minutes: Number(e.target.value) })} /></label>
      {error && <p className="text-sm text-red-700 sm:col-span-2">{error}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button className="btn-primary" disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={16} />} {t("Add visit")}</button>
        <button type="button" className="btn-ghost" onClick={onClose}>{t("Cancel")}</button>
      </div>
    </form>
  );
}
