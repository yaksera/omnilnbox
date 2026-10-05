"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { ArrowLeft, BookOpen, Copy, KeyRound, LoaderCircle, Plus, Send, Trash2, Webhook } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import type { ApiKeyRow, WebhookDeliveryRow, WebhookEndpoint } from "@/lib/types";
import { UpgradeHint } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

export default function DevelopersPage() {
  const t = useT();
  const [keys, setKeys] = useState<ApiKeyRow[] | null>(null);
  const [hooks, setHooks] = useState<{ events: Record<string, string>; endpoints: WebhookEndpoint[] } | null>(null);
  const [locked, setLocked] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [keyName, setKeyName] = useState("");
  const [hookForm, setHookForm] = useState<{ url: string; events: string[] }>({ url: "", events: ["message.received"] });
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDeliveryRow[]>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState("");

  const load = () => {
    Api.apiKeys().then(setKeys).catch((e) => { if (e instanceof ApiError && e.status === 402) setLocked(true); });
    Api.webhooks().then(setHooks).catch(() => undefined);
  };
  useEffect(load, []);

  async function run(key: string, fn: () => Promise<unknown>, ok?: string) {
    setBusy(key); setMsg(null);
    try { await fn(); if (ok) setMsg({ ok: true, text: ok }); load(); } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message.replace(/^\w+: /, "") : t("Failed") }); } finally { setBusy(""); }
  }

  const keyHelp = t("A key acts as you (same role) in this workspace. Send it as {code}. Keep it secret, like a password.").split("{code}");
  const hookHelp = t("We POST a JSON event to your HTTPS URL when something happens. Verify the {header} header (HMAC-SHA256 of the body with the endpoint secret).").split("{header}");

  const origin = typeof window === "undefined" ? "" : window.location.origin;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-6">
        <Link href="/settings" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={16} /> {t("Settings")}</Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">{t("API & webhooks")}</h1>
          <a href="/docs/api" target="_blank" rel="noreferrer" className="btn-secondary ml-auto"><BookOpen size={15} /> {t("API documentation")}</a>
        </div>
        {locked ? <UpgradeHint feature={t("API access")}>{t("Connect OmniInbox to your website, ERP, Google Sheets or Zapier with API keys and webhooks on the Business plan.")}</UpgradeHint> : (
          <>
            {msg && <p className={clsx("rounded-lg px-3 py-2 text-sm", msg.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-700")}>{msg.text}</p>}
            <section className="card p-5">
              <h2 className="flex items-center gap-2 font-semibold"><KeyRound size={18} /> {t("API keys")}</h2>
              <p className="mt-1 text-sm text-slate-600">{keyHelp[0]}<code className="rounded bg-slate-100 px-1">Authorization: Bearer omni_…</code>{keyHelp[1]}</p>
              {newKey && (
                <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <p className="text-sm font-medium text-amber-900">{t("Copy your new key now. You won’t see it again.")}</p>
                  <div className="mt-2 flex items-center gap-2"><code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1 text-xs">{newKey}</code>
                    <button type="button" className="btn-secondary px-2 py-1" onClick={() => navigator.clipboard.writeText(newKey)}><Copy size={14} /> {t("Copy")}</button></div>
                </div>
              )}
              <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); run("key", async () => { const k = await Api.createApiKey(keyName || t("API key")); setNewKey(k.key ?? null); setKeyName(""); }); }}>
                <input className="input" placeholder={t("Key name, e.g. Website orders / Zapier")} value={keyName} maxLength={80} onChange={(e) => setKeyName(e.target.value)} />
                <button className="btn-primary whitespace-nowrap" disabled={busy === "key"}><Plus size={15} /> {t("Create key")}</button>
              </form>
              <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {keys === null && <li className="p-3"><LoaderCircle className="animate-spin text-slate-400" size={16} /></li>}
                {keys?.length === 0 && <li className="p-3 text-sm text-slate-500">{t("No keys yet.")}</li>}
                {keys?.map((k) => (
                  <li key={k.id} className="flex items-center gap-3 p-3 text-sm">
                    <div className="min-w-0 flex-1"><p className="font-medium">{k.name} <code className="ml-1 text-xs text-slate-500">{k.prefix}…</code></p>
                      <p className="text-xs text-slate-500">{t("by {name}", { name: k.created_by })} · {t("created {date}", { date: new Date(k.created_at).toLocaleDateString() })} · {k.last_used_at ? t("last used {date}", { date: new Date(k.last_used_at).toLocaleString() }) : t("never used")}</p></div>
                    <button type="button" className="btn-ghost px-2 text-red-600" onClick={() => window.confirm(t("Revoke “{name}”? Apps using it stop working immediately.", { name: k.name })) && run(k.id, () => Api.revokeApiKey(k.id), t("Key revoked."))}>{t("Revoke")}</button>
                  </li>
                ))}
              </ul>
              <pre className="mt-4 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{`curl ${origin}/backend/conversations/?status=open \\
  -H "Authorization: Bearer omni_YOUR_KEY"`}</pre>
            </section>

            <section className="card p-5">
              <h2 className="flex items-center gap-2 font-semibold"><Webhook size={18} /> {t("Webhooks")}</h2>
              <p className="mt-1 text-sm text-slate-600">{hookHelp[0]}<code className="rounded bg-slate-100 px-1">X-Omni-Signature</code>{hookHelp[1]}</p>
              <form className="mt-4 space-y-3 rounded-lg border border-slate-200 p-3" onSubmit={(e) => { e.preventDefault(); run("hook", async () => { await Api.saveWebhook(null, hookForm); setHookForm({ url: "", events: ["message.received"] }); }, t("Webhook added. Send a test to check it.")); }}>
                <input className="input" type="url" required placeholder="https://your-server.com/omniinbox-webhook" value={hookForm.url} onChange={(e) => setHookForm({ ...hookForm, url: e.target.value })} />
                <div className="grid gap-1 sm:grid-cols-2">
                  {Object.entries(hooks?.events ?? {}).map(([k, label]) => (
                    <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand-600" checked={hookForm.events.includes(k)}
                      onChange={(e) => setHookForm({ ...hookForm, events: e.target.checked ? [...hookForm.events, k] : hookForm.events.filter((x) => x !== k) })} />
                      <code className="text-xs">{k}</code><span className="text-xs text-slate-500">{label}</span></label>
                  ))}
                </div>
                <button className="btn-primary" disabled={busy === "hook" || !hookForm.events.length}><Plus size={15} /> {t("Add webhook")}</button>
              </form>
              <div className="mt-4 space-y-3">
                {hooks?.endpoints.map((h) => (
                  <div key={h.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={clsx("h-2 w-2 rounded-full", !h.active ? "bg-slate-300" : h.last_status && h.last_status < 300 ? "bg-emerald-500" : h.last_status || h.last_error ? "bg-red-500" : "bg-slate-300")} />
                      <code className="min-w-0 flex-1 truncate">{h.url}</code>
                      <button type="button" className="btn-secondary px-2 py-1 text-xs" disabled={busy === h.id} onClick={() => run(h.id, async () => { const r = await Api.testWebhook(h.id); setMsg({ ok: r.ok, text: r.ok ? t("Test delivered (HTTP {status}).", { status: r.status ?? "" }) : t("Test failed: {error}", { error: r.error || `HTTP ${r.status}` }) }); })}><Send size={12} /> {t("Test")}</button>
                      <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => Api.webhookDeliveries(h.id).then((d) => setDeliveries({ ...deliveries, [h.id]: d }))}>{t("Log")}</button>
                      <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => run(h.id, () => Api.saveWebhook(h.id, { active: !h.active }))}>{h.active ? t("Pause") : t("Resume")}</button>
                      <button type="button" className="btn-ghost px-2 py-1 text-red-600" aria-label={t("Delete")} onClick={() => window.confirm(t("Delete this webhook?")) && run(h.id, () => Api.deleteWebhook(h.id))}><Trash2 size={14} /></button>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{h.events.join(", ")}{!h.active && h.failures >= 20 && ` · ${t("paused after {n} failed deliveries", { n: 20 })}`}</p>
                    <p className="mt-1 flex items-center gap-2 text-xs text-slate-500">{t("Secret:")} <code className="truncate">{h.secret}</code><button type="button" onClick={() => navigator.clipboard.writeText(h.secret)} aria-label={t("Copy secret")}><Copy size={12} /></button></p>
                    {h.last_error && <p className="mt-1 text-xs text-red-700">{t("Last error: {error}", { error: h.last_error })}</p>}
                    {deliveries[h.id] && (
                      <ul className="mt-2 max-h-48 overflow-y-auto rounded bg-slate-50 p-2 text-xs">
                        {deliveries[h.id].length === 0 && <li className="text-slate-500">{t("No deliveries yet.")}</li>}
                        {deliveries[h.id].map((d) => <li key={d.id} className="flex gap-2"><span className={d.status && d.status < 300 ? "text-emerald-700" : "text-red-700"}>{d.status ?? "ERR"}</span><code>{d.event}</code><span className="text-slate-400">{new Date(d.created_at).toLocaleString()} · {d.duration_ms} ms{d.attempts > 1 && ` · ${t("{n} tries", { n: d.attempts })}`}</span></li>)}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
