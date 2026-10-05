"use client";

import Link from "next/link";
import { useState } from "react";
import { LoaderCircle, MailCheck } from "lucide-react";
import { Api } from "@/lib/api";
import { AuthShell } from "@/components/AuthForm";
import { useT } from "@/lib/i18n";

export default function ForgotPasswordPage() {
  const t = useT();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<{ devLink?: string } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      const r = await Api.forgotPassword(email);
      setSent({ devLink: r.dev_link });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Something went wrong"));
    } finally { setLoading(false); }
  }

  const sentText = t("If an account exists for {email}, we've sent a link to choose a new password. It expires in 3 days. Check your spam folder too.").split("{email}");

  return (
    <AuthShell footer={<>{t("Remembered it?")} <Link href="/login" className="font-medium text-brand-600">{t("Log in")}</Link></>}>
      {sent ? (
        <div className="card space-y-3 p-6 text-center">
          <MailCheck className="mx-auto text-emerald-600" size={36} />
          <h1 className="text-lg font-semibold">{t("Check your email")}</h1>
          <p className="text-sm text-slate-600">{sentText[0]}<b>{email}</b>{sentText[1]}</p>
          {sent.devLink && (
            <p className="rounded-lg bg-amber-50 p-2 text-left text-xs text-amber-900">{t("Development mode (no email server set up):")} <a className="break-all font-medium underline" href={sent.devLink}>{t("open the reset link")}</a></p>
          )}
        </div>
      ) : (
        <form onSubmit={submit} className="card space-y-4 p-6">
          <h1 className="text-lg font-semibold">{t("Forgot your password?")}</h1>
          <p className="text-sm text-slate-600">{t("Enter your login email and we'll send you a link to choose a new one.")}</p>
          <input className="input" type="email" autoComplete="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <button className="btn-primary w-full" disabled={loading}>{loading && <LoaderCircle className="animate-spin" size={16} />} {t("Send reset link")}</button>
        </form>
      )}
    </AuthShell>
  );
}
