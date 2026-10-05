"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CircleCheck, LoaderCircle } from "lucide-react";
import { Api } from "@/lib/api";
import { AuthShell } from "@/components/AuthForm";
import { useT } from "@/lib/i18n";

export default function ResetPasswordPage() {
  const t = useT();
  const [params, setParams] = useState({ uid: "", token: "" });
  const [pw, setPw] = useState({ a: "", b: "" });
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setParams({ uid: q.get("uid") || "", token: q.get("token") || "" });
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pw.a !== pw.b) { setError(t("The two passwords don't match.")); return; }
    setLoading(true); setError("");
    try {
      await Api.resetPassword({ ...params, password: pw.a });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^password: /, "") : t("Something went wrong"));
    } finally { setLoading(false); }
  }

  return (
    <AuthShell>
      {done ? (
        <div className="card space-y-3 p-6 text-center">
          <CircleCheck className="mx-auto text-emerald-600" size={36} />
          <h1 className="text-lg font-semibold">{t("Password changed")}</h1>
          <p className="text-sm text-slate-600">{t("For your security we logged you out on every device. Log in with your new password.")}</p>
          <Link href="/login" className="btn-primary w-full">{t("Log in")}</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="card space-y-4 p-6">
          <h1 className="text-lg font-semibold">{t("Choose a new password")}</h1>
          {!params.token && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{t("Open this page from the link in your email.")}</p>}
          <label className="block text-sm"><span className="mb-1 block font-medium text-slate-700">{t("New password")}</span>
            <input className="input" type="password" autoComplete="new-password" minLength={8} value={pw.a} onChange={(e) => setPw({ ...pw, a: e.target.value })} required />
          </label>
          <label className="block text-sm"><span className="mb-1 block font-medium text-slate-700">{t("Repeat new password")}</span>
            <input className="input" type="password" autoComplete="new-password" minLength={8} value={pw.b} onChange={(e) => setPw({ ...pw, b: e.target.value })} required />
          </label>
          <p className="text-xs text-slate-500">{t("At least 8 characters, not too common, not only numbers.")}</p>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}{error.includes("expired") && <> <Link href="/forgot-password" className="font-medium underline">{t("Get a new link")}</Link></>}</p>}
          <button className="btn-primary w-full" disabled={loading || !params.token}>{loading && <LoaderCircle className="animate-spin" size={16} />} {t("Save new password")}</button>
        </form>
      )}
    </AuthShell>
  );
}
