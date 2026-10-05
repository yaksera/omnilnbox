"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BadgeCheck, Inbox, LoaderCircle, ShieldCheck } from "lucide-react";
import { Api, auth } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { clearStoredReferral, getStoredReferral, normalizeCode } from "@/lib/referral";

/** ?next=/affiliate -> go there after logging in. Only same-site paths, never another website. */
function nextPath() {
  const next = new URLSearchParams(window.location.search).get("next") ?? "";
  return /^\/(?![/\\])[\w\-/]*$/.test(next) ? next : "/inbox";
}

function LangToggle() {
  const { lang, setLang } = useLang();
  const opt = (l: "en" | "ne", label: string) => (
    <button type="button" onClick={() => setLang(l)} aria-pressed={lang === l}
      className={`rounded-md px-2 py-1 ${lang === l ? "bg-white font-medium text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
      {label}
    </button>
  );
  return (
    <div className="absolute right-4 top-4 flex items-center gap-0.5 rounded-lg bg-slate-100 p-0.5 text-xs">
      {opt("en", "English")}
      {opt("ne", "नेपाली")}
    </div>
  );
}

export function AuthShell({ children, footer }: { children: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <LangToggle />
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2 font-semibold">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white"><Inbox size={20} /></span>
          OmniInbox
        </Link>
        {children}
        {footer && <p className="mt-4 text-center text-sm text-slate-600">{footer}</p>}
      </div>
    </div>
  );
}

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const t = useT();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", password: "", workspace_name: "" });
  const [ticket, setTicket] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // affiliate promo code: typed in, or remembered from a tracking link (/r/CODE)
  const [promo, setPromo] = useState("");
  const [linkCode, setLinkCode] = useState("");
  const [referrer, setReferrer] = useState("");
  const [nextQuery, setNextQuery] = useState("");  // keep ?next= when switching between log in and sign up

  useEffect(() => {
    const next = nextPath();
    if (next !== "/inbox") setNextQuery(`?next=${encodeURIComponent(next)}`);
  }, []);

  useEffect(() => {
    if (mode !== "register") return;
    const stored = getStoredReferral();
    if (!stored) return;
    setPromo(stored.code);
    setLinkCode(stored.code);
    Api.affiliateCode(stored.code).then((r) => { if (r.valid) setReferrer(r.referrer || r.code); }).catch(() => undefined);
  }, [mode]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  function finish(tokens: { access: string; refresh: string }) {
    auth.clear();
    auth.set(tokens);
    router.push(nextPath());
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (ticket) {
        finish(await Api.loginTwoFactor(ticket, code));
      } else if (mode === "login") {
        const res = await Api.login({ email: form.email, password: form.password });
        if ("two_factor_required" in res) setTicket(res.ticket);
        else finish(res);
      } else {
        const code = normalizeCode(promo);
        const tokens = await Api.register({
          ...form, referral_code: code || undefined,
          referral_source: code && code === linkCode ? "link" : "code",
        });
        clearStoredReferral();
        finish(tokens);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^code: /, "") : t("Something went wrong"));
    } finally {
      setLoading(false);
    }
  }

  if (ticket) {
    return (
      <AuthShell footer={<button type="button" className="font-medium text-brand-600" onClick={() => { setTicket(""); setCode(""); }}>{t("Back to login")}</button>}>
        <form onSubmit={submit} className="card space-y-4 p-6">
          <h1 className="flex items-center gap-2 text-lg font-semibold"><ShieldCheck size={20} className="text-brand-600" /> {t("Two-factor login")}</h1>
          <p className="text-sm text-slate-600">{t("Open your authenticator app (Google Authenticator, Authy, Microsoft Authenticator) and enter the 6-digit code for OmniInbox. Lost your phone? Enter one of your recovery codes.")}</p>
          <input className="input text-center text-lg tracking-[0.3em]" autoFocus inputMode="text" autoComplete="one-time-code"
            placeholder="123456" maxLength={20} value={code} onChange={(e) => setCode(e.target.value)} required />
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <button className="btn-primary w-full" disabled={loading || code.trim().length < 6}>
            {loading && <LoaderCircle className="animate-spin" size={16} />} {t("Verify")}
          </button>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell footer={mode === "login"
      ? <>{t("No account?")} <Link href={`/register${nextQuery}`} className="font-medium text-brand-600">{t("Sign up")}</Link></>
      : <>{t("Already have an account?")} <Link href={`/login${nextQuery}`} className="font-medium text-brand-600">{t("Log in")}</Link></>}>
      <form onSubmit={submit} className="card space-y-4 p-6">
        <h1 className="text-lg font-semibold">{mode === "login" ? t("Welcome back") : t("Create your workspace")}</h1>
        {mode === "register" && (
          <>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">{t("Your name")}</span>
              <input className="input" value={form.name} onChange={set("name")} required autoComplete="name" />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">{t("Company / workspace")}</span>
              <input className="input" value={form.workspace_name} onChange={set("workspace_name")} placeholder="Acme Store" />
            </label>
          </>
        )}
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">{t("Email")}</span>
          <input className="input" type="email" value={form.email} onChange={set("email")} required autoComplete="email" />
        </label>
        <label className="block text-sm">
          <span className="mb-1 flex items-center justify-between font-medium text-slate-700">
            {t("Password")}
            {mode === "login" && <Link href="/forgot-password" className="text-xs font-normal text-brand-600">{t("Forgot password?")}</Link>}
          </span>
          <input className="input" type="password" value={form.password} onChange={set("password")} required minLength={8}
            autoComplete={mode === "login" ? "current-password" : "new-password"} />
        </label>
        {mode === "register" && (
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">{t("Promo code (optional)")}</span>
            <input className="input uppercase" value={promo} maxLength={20} autoComplete="off" placeholder="RAM2026"
              onChange={(e) => setPromo(normalizeCode(e.target.value))} />
            {referrer && promo === linkCode && (
              <span className="mt-1 flex items-center gap-1 text-xs text-emerald-700"><BadgeCheck size={14} /> {t("Referred by {name}", { name: referrer })}</span>
            )}
          </label>
        )}
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button className="btn-primary w-full" disabled={loading}>
          {loading && <LoaderCircle className="animate-spin" size={16} />}
          {mode === "login" ? t("Log in") : t("Create account")}
        </button>
        {mode === "register" && <p className="text-center text-xs text-slate-500">{t("14-day Pro trial. No card needed.")}</p>}
      </form>
    </AuthShell>
  );
}
