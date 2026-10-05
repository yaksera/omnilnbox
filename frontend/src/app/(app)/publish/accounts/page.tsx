"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, CircleAlert, LoaderCircle, Plus, Trash2 } from "lucide-react";
import { Api } from "@/lib/api";
import type { PublishConfig, SocialAccount } from "@/lib/types";
import { ProviderIcon, PUBLISH_PLATFORMS, providerUI } from "@/lib/providers";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";
import { fbLogin, loadSdk } from "@/components/channels/MetaConnect";
import { SiFacebook } from "react-icons/si";

const HELP: Record<string, string> = {
  facebook: "Log in with Facebook and pick your Pages. Every Page you choose is added, plus any Instagram professional account linked to it.",
  instagram: "Connected automatically through Facebook: link your Instagram professional account to your Facebook Page, then connect Facebook here.",
  youtube: "Sign in with the Google account that owns the channel.",
  tiktok: "Sign in with TikTok. Until TikTok approves your app, posts are visible only to you.",
};

export default function PublishAccountsPage() {
  const t = useT();
  const { can } = useMe();
  const manage = can("manage_social_accounts");
  const [cfg, setCfg] = useState<PublishConfig | null>(null);
  const [accounts, setAccounts] = useState<SocialAccount[] | null>(null);
  const [token, setToken] = useState("");
  const [pageId, setPageId] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = () => Api.socialAccounts().then(setAccounts).catch(() => setAccounts([]));

  useEffect(() => {
    Api.publishConfig().then(setCfg).catch(() => {});
    load();
    const q = new URLSearchParams(window.location.search);
    const c = q.get("connected");
    if (c) {
      setMsg(c === "error" ? { ok: false, text: q.get("message") || t("Connection failed.") }
        : { ok: true, text: t("{name} connected.", { name: providerUI(c).label }) });
      window.history.replaceState(null, "", "/publish/accounts");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connectFacebook(e: React.FormEvent) {
    e.preventDefault();
    setBusy("facebook"); setMsg(null);
    try {
      const res = await Api.connectFacebook({ access_token: token.trim(), page_id: pageId.trim() || undefined });
      setToken(""); setPageId("");
      setMsg({ ok: true, text: t("Connected {names}.", { names: res.accounts.map((a) => a.name).join(", ") }) });
      load();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : t("Couldn't connect") });
    } finally { setBusy(""); }
  }

  async function continueWithFacebook() {
    if (!cfg?.facebook_login) return;
    setBusy("facebook"); setMsg(null);
    try {
      const fb = cfg.facebook_login;
      const sdk = await loadSdk(fb.app_id, fb.graph_version);
      const accessToken = await fbLogin(sdk, { config_id: fb.config_id }, "accessToken");
      const res = await Api.connectFacebook({ access_token: accessToken, via: "facebook_login" });
      setMsg({ ok: true, text: t("Connected {names}.", { names: res.accounts.map((a) => a.name).join(", ") }) });
      load();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : t("Couldn't connect") });
    } finally { setBusy(""); }
  }

  async function oauth(platform: "youtube" | "tiktok") {
    setBusy(platform); setMsg(null);
    try {
      const { url } = await Api.socialOAuthStart(platform);
      window.location.assign(url);
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : t("Couldn't start sign-in") });
      setBusy("");
    }
  }

  async function remove(a: SocialAccount) {
    if (!window.confirm(t("Disconnect {name}? Scheduled posts to it will fail.", { name: a.name }))) return;
    setBusy(a.id);
    try { await Api.removeSocialAccount(a.id); load(); } finally { setBusy(""); }
  }

  if (!cfg || !accounts) return <div className="flex h-full items-center justify-center"><LoaderCircle className="animate-spin text-slate-400" /></div>;

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6">
      <Link href="/publish" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={16} /> {t("Publish")}</Link>
      <h1 className="mt-2 text-xl font-bold">{t("Publishing accounts")}</h1>
      <p className="text-sm text-slate-500">{t("{n} of {limit} accounts on your plan.", { n: accounts.length, limit: cfg.account_limit })}</p>

      {msg && <p className={`mt-4 rounded-lg px-3 py-2 text-sm ${msg.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-700"}`}>{msg.text}</p>}

      <div className="card mt-5 divide-y divide-slate-100">
        {accounts.length === 0 && <p className="p-5 text-sm text-slate-500">{t("No accounts connected yet.")}</p>}
        {accounts.map((a) => (
          <div key={a.id} className="flex items-center gap-3 p-4">
            <ProviderIcon provider={a.platform} size="md" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{a.name}</p>
              <p className="text-xs text-slate-500">{providerUI(a.platform).label}</p>
              {a.status === "error" && <p className="mt-0.5 flex items-center gap-1 text-xs text-red-700"><CircleAlert size={12} /> {a.last_error || t("Reconnect this account")}</p>}
            </div>
            {manage && (
              <button type="button" className="btn-ghost px-2 text-red-600" disabled={busy === a.id} onClick={() => remove(a)} aria-label={t("Disconnect {name}", { name: a.name })}>
                {busy === a.id ? <LoaderCircle className="animate-spin" size={16} /> : <Trash2 size={16} />}
              </button>
            )}
          </div>
        ))}
      </div>

      {manage ? (
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {PUBLISH_PLATFORMS.map((p) => {
            const info = cfg.platforms[p];
            return (
              <div key={p} className="card p-4">
                <div className="flex items-center gap-2">
                  <ProviderIcon provider={p} size="md" />
                  <p className="font-semibold">{info.label}</p>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-600">{t(HELP[p])}</p>
                {p === "facebook" && cfg.facebook_login && (
                  <button type="button" className="btn mt-3 w-full bg-[#1877F2] text-white hover:bg-[#166fe0]" disabled={!!busy} onClick={continueWithFacebook}>
                    {busy === "facebook" ? <LoaderCircle className="animate-spin" size={16} /> : <SiFacebook size={15} />} {t("Continue with Facebook")}
                  </button>
                )}
                {p === "facebook" && cfg.facebook_login && !showToken && (
                  <button type="button" className="mt-2 text-xs text-slate-500 underline hover:text-slate-700" onClick={() => setShowToken(true)}>
                    {t("Use a System User token instead")}
                  </button>
                )}
                {p === "facebook" && (!cfg.facebook_login || showToken) && (
                  <form onSubmit={connectFacebook} className="mt-3 space-y-2">
                    <p className="text-xs text-slate-500">{t("System User token (never expires) from Meta Business Settings with pages_show_list, pages_manage_posts, pages_read_engagement, instagram_basic and instagram_content_publish.")}</p>
                    <input className="input" type="password" autoComplete="off" placeholder={t("System User access token")} value={token} onChange={(e) => setToken(e.target.value)} required />
                    <input className="input" placeholder={t("Page ID (optional, to add just one Page)")} value={pageId} onChange={(e) => setPageId(e.target.value)} pattern="[0-9]*" />
                    <button className="btn-primary w-full" disabled={busy === "facebook" || !token.trim()}>
                      {busy === "facebook" ? <LoaderCircle className="animate-spin" size={16} /> : <Plus size={16} />} {t("Connect Facebook & Instagram")}
                    </button>
                  </form>
                )}
                {info.connect === "oauth" && (
                  info.enabled ? (
                    <button type="button" className="btn-primary mt-3 w-full" disabled={!!busy} onClick={() => oauth(p as "youtube" | "tiktok")}>
                      {busy === p ? <LoaderCircle className="animate-spin" size={16} /> : <Plus size={16} />} {t("Sign in with {name}", { name: info.label })}
                    </button>
                  ) : (
                    <p className="mt-3 rounded-lg bg-slate-50 p-2 text-xs text-slate-500">
                      {t("Not set up yet. Add {keys} to backend/.env and restart the server.", { keys: p === "youtube" ? "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET" : "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET" })}
                    </p>
                  )
                )}
              </div>
            );
          })}
        </div>
      ) : <p className="mt-6 text-sm text-slate-500">{t("Only owners and admins can connect or remove publishing accounts.")}</p>}
    </div>
  );
}
