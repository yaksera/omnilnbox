"use client";

import { useRef, useState } from "react";
import { CircleCheck, Gauge, ImagePlus, LoaderCircle, Palette, Trash } from "lucide-react";
import { Api } from "@/lib/api";
import { UpgradeHint, useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const SLA = [[0, "Off"], [15, "15 minutes"], [30, "30 minutes"], [60, "1 hour"], [120, "2 hours"], [240, "4 hours"], [1440, "1 day"]] as const;

export function QualitySection() {
  const t = useT();
  const { me, reloadMe, hasFeature } = useMe();
  const ws = me.workspace;
  const [question, setQuestion] = useState(ws.csat_question);
  const [saved, setSaved] = useState("");
  const done = (k: string) => { setSaved(k); setTimeout(() => setSaved(""), 2000); };

  return (
    <section className="card p-5" id="quality">
      <h2 className="flex items-center gap-2 font-semibold"><Gauge size={18} /> {t("Service quality")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t("Set a reply-time target and ask customers to rate your help.")}</p>
      <label className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">{t("First-reply target (SLA)")}</span>
        <select className="input w-40" value={ws.sla_minutes} onChange={async (e) => { await Api.updateWorkspace({ sla_minutes: Number(e.target.value) }); await reloadMe(); done("sla"); }}>
          {SLA.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
        </select>
        {saved === "sla" && <CircleCheck size={16} className="text-emerald-600" />}
      </label>
      <p className="mt-1 text-xs text-slate-500">{t("Conversations waiting longer than this get a red timer in the inbox, and Analytics shows how often you hit the target.")}</p>
      <div className="mt-5 border-t border-slate-100 pt-4">
        {!hasFeature("csat") ? <UpgradeHint feature={t("Satisfaction surveys")}>{t("Ask customers to rate your help after each chat on the Pro plan and above.")}</UpgradeHint> : (
          <>
            <label className="flex items-start gap-3">
              <input type="checkbox" className="mt-1 h-4 w-4 accent-brand-600" checked={ws.csat_enabled}
                onChange={async (e) => { await Api.updateWorkspace({ csat_enabled: e.target.checked }); await reloadMe(); }} />
              <span><span className="block text-sm font-medium">{t("Send a satisfaction survey (CSAT) when a conversation is closed")}</span>
                <span className="block text-xs text-slate-500">{t("Only for chats a person answered (not email). Customers reply 1–5 (or ⭐⭐⭐⭐⭐); replies don’t reopen the chat.")}</span></span>
            </label>
            {ws.csat_enabled && (
              <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={async (e) => { e.preventDefault(); await Api.updateWorkspace({ csat_question: question }); await reloadMe(); done("q"); }}>
                <input className="input" maxLength={300} value={question} onChange={(e) => setQuestion(e.target.value)} />
                <button className="btn-secondary">{saved === "q" ? <CircleCheck size={15} /> : null} {t("Save")}</button>
              </form>
            )}
          </>
        )}
      </div>
    </section>
  );
}

export function BrandingSection() {
  const t = useT();
  const { me, reloadMe, hasFeature } = useMe();
  const b = me.workspace.brand;
  const [name, setName] = useState(b.name);
  const [color, setColor] = useState(b.color || "#4f46e5");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);

  if (!hasFeature("white_label")) {
    return (
      <section className="card p-5"><h2 className="flex items-center gap-2 font-semibold"><Palette size={18} /> {t("White-label branding")}</h2>
        <div className="mt-3"><UpgradeHint feature={t("White-label")}>{t("Use your own name, logo and colours for your team and customers (great for agencies) on the Business plan.")}</UpgradeHint></div></section>
    );
  }
  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await fn(); await reloadMe(); } catch (err) { setError(err instanceof Error ? err.message.replace(/^\w+: /, "") : t("Failed")); } finally { setBusy(false); }
  }
  return (
    <section className="card p-5" id="branding">
      <h2 className="flex items-center gap-2 font-semibold"><Palette size={18} /> {t("White-label branding")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t("Shown to your team (app sidebar and colours) and your customers (payment pages and website chat).")}</p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <button type="button" onClick={() => file.current?.click()} className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl border-2 border-dashed border-slate-300 text-slate-400 hover:border-brand-400">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {b.logo_url ? <img src={b.logo_url} alt={t("Logo")} className="h-full w-full object-contain" /> : <ImagePlus />}
        </button>
        <input ref={file} type="file" accept="image/png,image/jpeg" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => Api.uploadBrandLogo(f)); e.target.value = ""; }} />
        {b.logo_url && <button type="button" className="btn-ghost text-red-600" onClick={() => run(() => Api.removeBrandLogo())}><Trash size={14} /> {t("Remove logo")}</button>}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="text-sm">{t("Brand name")}<input className="input mt-1" maxLength={60} placeholder={me.workspace.name} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="text-sm">{t("Main colour")}
          <span className="mt-1 flex items-center gap-2"><input type="color" className="h-10 w-12 rounded border border-slate-300" value={color} onChange={(e) => setColor(e.target.value)} />
            <input className="input w-28 font-mono" value={color} onChange={(e) => setColor(e.target.value)} /></span>
        </label>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand-600" checked={b.hide_powered_by} onChange={(e) => run(() => Api.saveBrand({ hide_powered_by: e.target.checked }))} /> {t("Hide “Powered by OmniInbox” on payment pages and the website chat")}</label>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      <button type="button" className="btn-primary mt-4" disabled={busy} onClick={() => run(() => Api.saveBrand({ brand_name: name, brand_color: color }))}>{busy && <LoaderCircle className="animate-spin" size={15} />} {t("Save branding")}</button>
    </section>
  );
}
