"use client";

import { useState } from "react";
import clsx from "clsx";
import { Bot, CheckCircle2, CircleAlert, Clock, LoaderCircle, Moon, Power, Sun } from "lucide-react";
import { Api } from "@/lib/api";
import type { AISettings, BotMode, Weekday } from "@/lib/types";
import { UpgradeHint } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const DAYS: Array<[Weekday, string]> = [["sun", "Sunday"], ["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"]];
const MODES: Array<[BotMode, string, string, typeof Power]> = [
  ["off", "Off", "The AI only helps your agents (suggestions, summaries). It never messages customers by itself.", Power],
  ["after_hours", "Outside business hours", "Your team answers during the day. At night and on holidays the AI answers.", Moon],
  ["always", "24/7", "The AI answers every new message right away and hands tricky ones to your team.", Sun],
];

export default function AssistantTab({ cfg, canEdit, onSaved }: { cfg: AISettings; canEdit: boolean; onSaved: (c: AISettings) => void }) {
  const t = useT();
  const [form, setForm] = useState(cfg);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const set = <K extends keyof AISettings>(k: K, v: AISettings[K]) => setForm({ ...form, [k]: v });
  const pct = cfg.credits.limit ? Math.min(100, Math.round((cfg.credits.used / cfg.credits.limit) * 100)) : 100;

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const { business_name, about, tone, bot_name, bot_mode, handoff_message, auto_tag, timezone, hours } = form;
      const next = await Api.saveAISettings({ business_name, about, tone, bot_name, bot_mode, handoff_message, auto_tag, timezone, hours });
      onSaved(next); setForm(next);
      setMsg({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : t("Couldn't save") });
    } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="space-y-5">
        {!cfg.configured && (
          <p className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <CircleAlert size={18} className="shrink-0" />
            <span>{t("AI isn't connected yet.")} {t("Add")} <code className="rounded bg-amber-100 px-1">OPENROUTER_API_KEY</code> → <code className="rounded bg-amber-100 px-1">backend/.env</code>. <b>{t("Then stop the backend (Ctrl+C) and start it again")}</b>: {t("auto-reload doesn't pick up .env changes. Refresh this page afterwards. You can still set everything up now.")}</span>
          </p>
        )}

        <section className="card p-5">
          <h2 className="font-semibold">{t("Your business")}</h2>
          <p className="text-sm text-slate-500">{t("The AI uses this and the knowledge base to answer. It never makes up prices or promises.")}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-sm">{t("Business name")}
              <input className="input mt-1" value={form.business_name} maxLength={120} disabled={!canEdit} onChange={(e) => set("business_name", e.target.value)} />
            </label>
            <label className="text-sm">{t("Assistant name")}
              <input className="input mt-1" value={form.bot_name} maxLength={40} disabled={!canEdit} onChange={(e) => set("bot_name", e.target.value)} />
            </label>
          </div>
          <label className="mt-3 block text-sm">{t("About the business")}
            <textarea className="input mt-1 min-h-[120px]" maxLength={3000} disabled={!canEdit} value={form.about} onChange={(e) => set("about", e.target.value)}
              placeholder={t("e.g. We sell handmade cotton kurtas and sarees from our shop in New Road, Kathmandu. Delivery all over Nepal in 2-4 days (Rs 100 inside the Valley, Rs 150 outside). Payment: cash on delivery, Khalti or eSewa. Exchange within 7 days, no refunds on sale items.")} />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            {(["friendly", "professional", "casual"] as const).map((tone) => (
              <button key={tone} type="button" disabled={!canEdit} onClick={() => set("tone", tone)}
                className={clsx("rounded-full border px-3 py-1 text-sm capitalize", form.tone === tone ? "border-brand-500 bg-brand-50 text-brand-800" : "border-slate-200 text-slate-600")}>{t(tone)}</button>
            ))}
            <span className="self-center text-xs text-slate-500">{t("tone")}</span>
          </div>
        </section>

        <section className="card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><Bot size={18} /> {t("AI chatbot")}</h2>
          {!cfg.features.bot && <div className="mt-3"><UpgradeHint feature={t("The 24/7 AI chatbot")}>{t("The chatbot that answers customers by itself is on Pro and higher. Reply suggestions work on every plan.")}</UpgradeHint></div>}
          <div className="mt-4 grid gap-2">
            {MODES.map(([key, label, help, Icon]) => (
              <button key={key} type="button" disabled={!canEdit || (!cfg.features.bot && key !== "off")} onClick={() => set("bot_mode", key)}
                className={clsx("flex items-start gap-3 rounded-xl border p-3 text-left disabled:opacity-50",
                  form.bot_mode === key ? "border-brand-500 bg-brand-50/60 ring-1 ring-brand-500" : "border-slate-200 hover:border-slate-300")}>
                <Icon size={18} className={form.bot_mode === key ? "mt-0.5 text-brand-600" : "mt-0.5 text-slate-400"} />
                <span><span className="block text-sm font-medium">{t(label)}</span><span className="block text-xs text-slate-500">{t(help)}</span></span>
              </button>
            ))}
          </div>
          <label className="mt-4 block text-sm">{t("Message when handing over to your team")}
            <input className="input mt-1" maxLength={500} disabled={!canEdit} value={form.handoff_message} onChange={(e) => set("handoff_message", e.target.value)} />
            <span className="text-xs text-slate-500">{t("The AI hands over for orders, payments, refunds, complaints, or anything it doesn't know. It writes this message in the customer's own language.")}</span>
          </label>
          <label className="mt-4 flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 accent-brand-600" checked={form.auto_tag} disabled={!canEdit} onChange={(e) => set("auto_tag", e.target.checked)} />
            <span><b>{t("Auto-label new conversations")}</b> {t("as Order, Lead, Question, Complaint, Support, Feedback or Spam, so your team sees what matters first. Uses 1 credit per new conversation.")}</span>
          </label>
        </section>

        <section className="card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><Clock size={18} /> {t("Business hours")}
            <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", cfg.is_open ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600")}>{cfg.is_open ? t("Open now") : t("Closed now")}</span>
          </h2>
          <p className="text-sm text-slate-500">{t("Used by “Outside business hours” mode and away messages.")}</p>
          <label className="mt-3 block max-w-xs text-sm">{t("Time zone")}
            <select className="input mt-1" value={form.timezone} disabled={!canEdit} onChange={(e) => set("timezone", e.target.value)}>
              {["Asia/Kathmandu", "Asia/Kolkata", "Asia/Dubai", "Asia/Qatar", "Asia/Riyadh", "Asia/Tokyo", "Australia/Sydney", "Europe/London", "America/New_York", "UTC"].map((z) => <option key={z}>{z}</option>)}
            </select>
          </label>
          <div className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {DAYS.map(([d, label]) => {
              const h = form.hours[d];
              return (
                <div key={d} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                  <label className="flex w-32 items-center gap-2">
                    <input type="checkbox" className="accent-brand-600" checked={h.on} disabled={!canEdit} onChange={(e) => set("hours", { ...form.hours, [d]: { ...h, on: e.target.checked } })} />
                    {t(label)}
                  </label>
                  {h.on ? (
                    <span className="flex items-center gap-2">
                      <input type="time" className="input w-28 py-1" value={h.start} disabled={!canEdit} onChange={(e) => set("hours", { ...form.hours, [d]: { ...h, start: e.target.value } })} />
                      {t("to")}
                      <input type="time" className="input w-28 py-1" value={h.end} disabled={!canEdit} onChange={(e) => set("hours", { ...form.hours, [d]: { ...h, end: e.target.value } })} />
                    </span>
                  ) : <span className="text-slate-400">{t("Closed")}</span>}
                </div>
              );
            })}
          </div>
        </section>

        {canEdit && (
          <div className="flex items-center gap-3">
            <button type="button" className="btn-primary" onClick={save} disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={16} />} {t("Save settings")}</button>
            {msg && <span className={clsx("text-sm", msg.ok ? "text-emerald-700" : "text-red-700")}>{msg.ok && <CheckCircle2 size={14} className="mr-1 inline" />}{msg.text}</span>}
          </div>
        )}
      </div>

      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <div className="card p-4">
          <p className="text-sm font-semibold">{t("AI credits this month")}</p>
          <p className="mt-1 text-2xl font-bold">{cfg.credits.used.toLocaleString()} <span className="text-base font-normal text-slate-500">/ {cfg.credits.limit.toLocaleString()}</span></p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className={clsx("h-full rounded-full", pct >= 90 ? "bg-red-500" : "bg-brand-600")} style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">{t("1 credit = 1 AI reply, suggestion, summary or caption. Resets on the 1st of each month.")}</p>
        </div>
        <div className="card p-4 text-xs text-slate-600">
          <p className="text-sm font-semibold text-slate-900">{t("How the AI stays safe")}</p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>{t("Answers only from your business info and knowledge base.")}</li>
            <li>{t("Replies in the customer's language: Nepali, Romanized Nepali or English.")}</li>
            <li>{t("Hands over to a person for orders, payments and complaints.")}</li>
            <li>{t("Stops in a conversation as soon as your agent replies. Closing the conversation turns it back on.")}</li>
          </ul>
          <p className="mt-2 text-slate-400">{t("Model: {model}", { model: cfg.model })}</p>
        </div>
      </aside>
    </div>
  );
}
