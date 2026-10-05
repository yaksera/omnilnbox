"use client";

import { useState } from "react";
import { CircleCheck, Copy, LoaderCircle, ShieldCheck, ShieldOff } from "lucide-react";
import { Api } from "@/lib/api";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

export default function SecuritySection() {
  const t = useT();
  const { me, reloadMe } = useMe();
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const on = me.user.two_factor_enabled;
  const step1 = t("In your authenticator app tap {plus} and scan this QR code.").split("{plus}");

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError("");
    try { await fn(); } catch (err) { setError(err instanceof Error ? err.message.replace(/^(code|password): /, "") : t("Failed")); } finally { setBusy(false); }
  }

  return (
    <section className="card p-5" id="security">
      <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck size={18} /> {t("Two-factor login")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t("Protect your account with a 6-digit code from an authenticator app (Google Authenticator, Microsoft Authenticator, Authy) on top of your password.")}</p>

      {codes ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="flex items-center gap-2 font-medium text-amber-900"><CircleCheck size={16} /> {t("Two-factor login is on. Save your recovery codes now.")}</p>
          <p className="mt-1 text-sm text-amber-900">{t("If you lose your phone, each code logs you in once. We won’t show them again.")}</p>
          <div className="mt-3 grid grid-cols-2 gap-1 rounded bg-white p-3 font-mono text-sm sm:grid-cols-5">{codes.map((c) => <span key={c}>{c}</span>)}</div>
          <div className="mt-3 flex gap-2">
            <button type="button" className="btn-secondary" onClick={() => navigator.clipboard.writeText(codes.join("\n"))}><Copy size={14} /> {t("Copy")}</button>
            <button type="button" className="btn-primary" onClick={() => setCodes(null)}>{t("I’ve saved them")}</button>
          </div>
        </div>
      ) : on ? (
        <div className="mt-4 space-y-3">
          <p className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700"><CircleCheck size={15} /> {t("On")}</p>
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); run(async () => { await Api.twoFactorDisable(password); setPassword(""); await reloadMe(); }); }}>
            <input className="input sm:w-64" type="password" placeholder={t("Your password to turn it off")} value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
            <button className="btn-secondary text-red-600" disabled={busy}><ShieldOff size={15} /> {t("Turn off")}</button>
          </form>
        </div>
      ) : setup ? (
        <div className="mt-4 grid gap-4 sm:grid-cols-[200px_1fr]">
          <div className="rounded-lg border border-slate-200 bg-white p-2 [&_svg]:h-auto [&_svg]:w-full" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <div className="space-y-3 text-sm">
            <p><b>1.</b> {step1[0]}<b>+</b>{step1[1]}</p>
            <p className="text-slate-500">{t("Can’t scan? Enter this key:")} <code className="break-all rounded bg-slate-100 px-1.5 py-0.5">{setup.secret}</code></p>
            <p><b>2.</b> {t("Enter the 6-digit code the app shows:")}</p>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { const r = await Api.twoFactorEnable(code); setCodes(r.recovery_codes); setSetup(null); setCode(""); await reloadMe(); }); }}>
              <input className="input w-36 text-center tracking-widest" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required />
              <button className="btn-primary" disabled={busy || code.length !== 6}>{busy && <LoaderCircle className="animate-spin" size={15} />} {t("Turn on")}</button>
            </form>
          </div>
        </div>
      ) : (
        <button type="button" className="btn-primary mt-4" disabled={busy} onClick={() => run(async () => setSetup(await Api.twoFactorSetup()))}>
          {busy && <LoaderCircle className="animate-spin" size={15} />} {t("Set up two-factor login")}
        </button>
      )}
      {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
    </section>
  );
}
