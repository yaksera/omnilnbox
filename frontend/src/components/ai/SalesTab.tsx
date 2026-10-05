"use client";

import Link from "next/link";
import { useState } from "react";
import clsx from "clsx";
import { BellRing, CalendarCheck, CheckCircle2, CircleAlert, LoaderCircle, Mic, Receipt, ShoppingBag } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Api } from "@/lib/api";
import type { AISettings } from "@/lib/types";
import { UpgradeHint } from "@/components/AppShell";
import { useT } from "@/lib/i18n";
import AIReportCard from "./AIReportCard";

const LABELS = ["Counselling session", "Campus visit", "Appointment", "Trial class", "Consultation", "Store visit"];

function Feature({ icon: Icon, title, help, on, onChange, disabled, children }: {
  icon: LucideIcon; title: string; help: string; on: boolean; onChange: (v: boolean) => void; disabled?: boolean; children?: React.ReactNode;
}) {
  return (
    <section className={clsx("card p-4 sm:p-5", on && "ring-1 ring-brand-300")}>
      <div className="flex items-start gap-3">
        <span className={clsx("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl", on ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-500")}><Icon size={20} /></span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{title}</p>
          <p className="text-sm text-slate-500">{help}</p>
        </div>
        <button type="button" role="switch" aria-checked={on} aria-label={title} disabled={disabled} onClick={() => onChange(!on)}
          className={clsx("relative mt-1 h-6 w-11 shrink-0 rounded-full transition disabled:opacity-40", on ? "bg-brand-600" : "bg-slate-300")}>
          <span className={clsx("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", on ? "left-[22px]" : "left-0.5")} />
        </button>
      </div>
      {on && children && <div className="mt-4 border-t border-slate-100 pt-4">{children}</div>}
    </section>
  );
}

export default function SalesTab({ cfg, canEdit, onSaved, goAssistant }: {
  cfg: AISettings; canEdit: boolean; onSaved: (c: AISettings) => void; goAssistant: () => void;
}) {
  const t = useT();
  const [form, setForm] = useState(cfg);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const set = <K extends keyof AISettings>(k: K, v: AISettings[K]) => { setForm((f) => ({ ...f, [k]: v })); setMsg(null); };
  const ordersAllowed = cfg.features.orders;

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const { sales_orders, sales_bookings, booking_label, booking_minutes, booking_capacity, followup_enabled, followup_hours, voice_notes, check_payments } = form;
      const next = await Api.saveAISettings({ sales_orders, sales_bookings, booking_label, booking_minutes, booking_capacity, followup_enabled, followup_hours, voice_notes, check_payments });
      onSaved(next); setForm(next);
      setMsg({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : t("Couldn't save") });
    } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="space-y-4">
        <div className="rounded-2xl bg-gradient-to-br from-brand-600 to-indigo-600 p-5 text-white">
          <p className="text-lg font-bold">{t("Your AI sales staff")}</p>
          <p className="mt-1 text-sm text-white/85">{t("It answers, recommends, takes the order or books the visit, understands voice notes, checks payment screenshots and follows up when customers go quiet. You wake up to orders and bookings, not unread messages.")}</p>
        </div>

        {cfg.bot_mode === "off" && (
          <p className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <CircleAlert size={18} className="shrink-0" />
            <span>{t("The AI chatbot is off, so it won't sell or book by itself yet.")}{" "}
              <button type="button" className="font-semibold underline" onClick={goAssistant}>{t("Turn on the chatbot")}</button></span>
          </p>
        )}

        <Feature icon={ShoppingBag} title={t("Take orders in chat")} on={form.sales_orders} disabled={!canEdit || !ordersAllowed} onChange={(v) => set("sales_orders", v)}
          help={t("Recommends products, collects name, phone and address, sends a summary with real prices and creates the order when the customer says YES.")}>
          <p className="text-sm text-slate-600">{t("The AI only sells what's in")} <Link href="/products" className="font-medium text-brand-700 underline">{t("Products")}</Link>{t(", with your prices, options and stock. Delivery charges come from Settings → Shop.")}</p>
        </Feature>
        {!ordersAllowed && <UpgradeHint feature={t("Orders")}>{t("Taking orders and checking payments need a plan with Orders (Starter and higher).")}</UpgradeHint>}

        <Feature icon={CalendarCheck} title={t("Book visits & appointments")} on={form.sales_bookings} disabled={!canEdit} onChange={(v) => set("sales_bookings", v)}
          help={t("For consultancies, schools, clinics and salons: the AI finds a free time inside your business hours and books it.")}>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm sm:col-span-3">{t("What is booked")}
              <input className="input mt-1" value={form.booking_label} maxLength={60} disabled={!canEdit} onChange={(e) => set("booking_label", e.target.value)} />
              <span className="mt-1.5 flex flex-wrap gap-1.5">
                {LABELS.map((l) => (
                  <button key={l} type="button" disabled={!canEdit} onClick={() => set("booking_label", l)}
                    className={clsx("rounded-full border px-2.5 py-0.5 text-xs", form.booking_label === l ? "border-brand-500 bg-brand-50 text-brand-800" : "border-slate-200 text-slate-600")}>{t(l)}</button>
                ))}
              </span>
            </label>
            <label className="text-sm">{t("Length (minutes)")}
              <input type="number" className="input mt-1" min={10} max={240} step={5} value={form.booking_minutes} disabled={!canEdit} onChange={(e) => set("booking_minutes", Number(e.target.value))} />
            </label>
            <label className="text-sm">{t("People at the same time")}
              <input type="number" className="input mt-1" min={1} max={50} value={form.booking_capacity} disabled={!canEdit} onChange={(e) => set("booking_capacity", Number(e.target.value))} />
            </label>
            <p className="self-end text-xs text-slate-500 sm:pb-2">{t("Opening hours come from the AI assistant tab.")} <Link href="/visits" className="text-brand-700 underline">{t("See visits")}</Link></p>
          </div>
        </Feature>

        <Feature icon={BellRing} title={t("Follow up when customers go quiet")} on={form.followup_enabled} disabled={!canEdit} onChange={(v) => set("followup_enabled", v)}
          help={t("If someone was interested but stopped replying, the AI sends one friendly nudge. Never more than once, and never if anyone has written since.")}>
          <label className="block max-w-xs text-sm">{t("Follow up after (hours)")}
            <input type="number" className="input mt-1" min={1} max={47} value={form.followup_hours} disabled={!canEdit} onChange={(e) => set("followup_hours", Number(e.target.value))} />
          </label>
          <p className="mt-2 text-xs text-slate-500">{t("Messenger, Instagram and WhatsApp only allow business messages within 24 hours of the customer's last message, so there the follow-up is sent within 22 hours at the latest.")}</p>
        </Feature>

        <Feature icon={Mic} title={t("Understand voice messages")} on={form.voice_notes} disabled={!canEdit} onChange={(v) => set("voice_notes", v)}
          help={t("Nepali and English voice notes are written out, so the AI can reply and your team can read them instead of listening. 1 credit per voice note.")} />

        <Feature icon={Receipt} title={t("Check payment screenshots")} on={form.check_payments} disabled={!canEdit || !ordersAllowed} onChange={(v) => set("check_payments", v)}
          help={t("Reads eSewa, Khalti, Fonepay and bank screenshots, matches the amount to the order and flags fakes: reused transaction IDs, wrong receiver, old dates, edits. Staff confirm with one tap.")}>
          <p className="text-sm text-slate-600">{t("Add how your account appears on screenshots in")} <Link href="/settings/shop" className="font-medium text-brand-700 underline">{t("Settings → Shop")}</Link>{t(" so the receiver can be checked.")}</p>
        </Feature>

        {canEdit && (
          <div className="sticky bottom-0 -mx-4 flex items-center gap-3 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
            <button type="button" className="btn-primary" onClick={save} disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={16} />} {t("Save settings")}</button>
            {msg && <span className={clsx("text-sm", msg.ok ? "text-emerald-700" : "text-red-700")}>{msg.ok && <CheckCircle2 size={14} className="mr-1 inline" />}{msg.text}</span>}
          </div>
        )}
      </div>
      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <AIReportCard />
        <div className="card p-4 text-xs text-slate-600">
          <p className="text-sm font-semibold text-slate-900">{t("Safe by design")}</p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>{t("Prices and stock always come from your catalogue, never from the AI.")}</li>
            <li>{t("Orders are only created after the customer confirms the summary.")}</li>
            <li>{t("The AI never marks anything paid. Your team confirms payments.")}</li>
            <li>{t("Refunds, complaints and unknown questions still go to your team.")}</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
