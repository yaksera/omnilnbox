"use client";

import { useCallback, useEffect, useState } from "react";
import { FacebookConnect, useMetaConfig } from "@/components/channels/MetaConnect";
import clsx from "clsx";
import {
  CircleAlert, CircleCheck, Clock, Copy, ExternalLink, LoaderCircle, Plus, RefreshCw, Sparkles, Trash, X, Zap,
} from "lucide-react";
import { Api } from "@/lib/api";
import type { Channel, ProviderMeta } from "@/lib/types";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { timeAgo } from "@/lib/format";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const MASK = "••••••••";

type Notice = { kind: "ok" | "err"; text: string; vars?: Record<string, string | number> };

/** Puts React nodes in place of {name} placeholders in an already translated sentence. */
function rich(text: string, nodes: Record<string, React.ReactNode>) {
  return text.split(/(\{\w+\})/).map((part, i) => {
    const m = /^\{(\w+)\}$/.exec(part);
    return m && m[1] in nodes ? <span key={i}>{nodes[m[1]]}</span> : part;
  });
}

function CopyField({ label, value }: { label: string; value: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <div className="text-xs">
      <p className="mb-1 font-medium text-slate-500">{label}</p>
      <div className="flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1.5 font-mono">
        <span className="flex-1 truncate">{value}</span>
        <button
          type="button"
          className="text-slate-500 hover:text-slate-800"
          onClick={() => {
            navigator.clipboard?.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
          title={t("Copy")}
        >
          {copied ? <CircleCheck size={14} /> : <Copy size={14} />}
        </button>
      </div>
    </div>
  );
}

function StatusPill({ channel }: { channel: Channel }) {
  const t = useT();
  const map = {
    active: ["bg-emerald-50 text-emerald-700", "Active", CircleCheck],
    pending: ["bg-amber-50 text-amber-700", "Needs setup", Clock],
    error: ["bg-red-50 text-red-700", "Error", CircleAlert],
    disabled: ["bg-slate-100 text-slate-600", "Disabled", Clock],
  } as const;
  const [cls, label, Icon] = map[channel.status];
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", cls)}>
      <Icon size={12} /> {t(label)}
    </span>
  );
}

export default function ChannelsPage() {
  const { me, can } = useMe();
  const t = useT();
  const [providers, setProviders] = useState<ProviderMeta[]>([]);
  const [channels, setChannels] = useState<Channel[] | null>(null);
  const [editing, setEditing] = useState<{ provider: ProviderMeta; channel?: Channel } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const metaCfg = useMetaConfig();

  const reload = useCallback(async () => setChannels(await Api.channels()), []);

  useEffect(() => {
    Api.providers().then(setProviders);
    reload();
    const params = new URLSearchParams(window.location.search);
    if (params.get("oauth") === "success") setNotice({ kind: "ok", text: "Account authorized successfully." });
    if (params.get("oauth") === "error") setNotice({ kind: "err", text: "Authorization failed: {message}", vars: { message: params.get("message") ?? "" } });
  }, [reload]);

  const canManage = can("manage_channels");
  const realCount = channels?.filter((c) => !c.is_demo).length ?? 0;
  const hasDemo = channels?.some((c) => c.is_demo);

  async function run(id: string, fn: () => Promise<unknown>, okText?: string) {
    setBusy(id);
    setNotice(null);
    try {
      await fn();
      if (okText) setNotice({ kind: "ok", text: okText });
    } catch (err) {
      setNotice({ kind: "err", text: err instanceof Error ? err.message : "Failed" });
    } finally {
      setBusy(null);
      reload();
    }
  }

  async function authorize(channel: Channel) {
    setBusy(channel.id);
    try {
      const { url } = await Api.oauthStart(channel.id);
      window.location.href = url;
    } catch (err) {
      setNotice({ kind: "err", text: err instanceof Error ? err.message : "Failed" });
      setBusy(null);
    }
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{t("Channels")}</h1>
            <p className="mt-1 text-sm text-slate-600">
              {t("{used} of {limit} channels used on the {plan} plan.", {
                used: realCount,
                limit: me.workspace.channel_limit,
                plan: me.workspace.plan.charAt(0).toUpperCase() + me.workspace.plan.slice(1),
              })}
            </p>
          </div>
          {canManage && (
            hasDemo ? (
              <button className="btn-secondary" onClick={() => run("demo", () => Api.clearDemo(), "Demo data removed.")} disabled={busy === "demo"}>
                <Trash size={16} /> {t("Remove demo data")}
              </button>
            ) : (
              <button className="btn-secondary" onClick={() => run("demo", () => Api.loadDemo(), "Demo channels loaded — check your inbox.")} disabled={busy === "demo"}>
                <Sparkles size={16} /> {t("Load demo data")}
              </button>
            )
          )}
        </div>

        {notice && (
          <div className={clsx("mt-4 flex items-start gap-2 rounded-lg px-4 py-3 text-sm",
            notice.kind === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800")}>
            {notice.kind === "ok" ? <CircleCheck size={18} /> : <CircleAlert size={18} />}
            <span className="flex-1 break-words">{t(notice.text, notice.vars)}</span>
            <button onClick={() => setNotice(null)} aria-label={t("Close")}><X size={16} /></button>
          </div>
        )}

        {/* Connected channels */}
        <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-slate-500">{t("Connected")}</h2>
        {channels === null ? (
          <div className="flex justify-center p-8 text-slate-400"><LoaderCircle className="animate-spin" /></div>
        ) : channels.length === 0 ? (
          <p className="card p-6 text-sm text-slate-500">{t("No channels yet. Pick a platform below to connect it.")}</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {channels.map((ch) => {
              const meta = providers.find((p) => p.key === ch.provider);
              return (
                <div key={ch.id} className="card p-4">
                  <div className="flex items-start gap-3">
                    <ProviderIcon provider={ch.provider} size="lg" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-semibold">{ch.name}</p>
                        <StatusPill channel={ch} />
                        {ch.is_demo && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">{t("demo")}</span>}
                      </div>
                      <p className="text-xs text-slate-500">
                        {providerUI(ch.provider).label} · {t("receives via {mode}", { mode: ch.receive_mode })}
                        {ch.last_synced_at && <> · {t("synced {time} ago", { time: timeAgo(ch.last_synced_at) })}</>}
                        {!!ch.unread_count && <> · {t("{n} unread", { n: ch.unread_count })}</>}
                      </p>
                    </div>
                  </div>

                  {ch.last_error && <p className="mt-3 break-words rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{ch.last_error}</p>}

                  {!ch.is_demo && ch.receive_mode.includes("webhook") && (
                    <div className="mt-3 space-y-2">
                      {!ch.webhook_public && (
                        <div className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
                          <p className="font-semibold">{t("This webhook URL is not reachable from the internet, so no messages will arrive.")}</p>
                          <p className="mt-1">
                            {rich(t("Run a tunnel (e.g. {cmd}), set {var} in {file} to the https URL it prints, restart Django, then paste the new URL below into the platform's webhook settings."), {
                              cmd: <code>ngrok http 8000</code>, var: <code>PUBLIC_BASE_URL</code>, file: <code>backend/.env</code>,
                            })}
                          </p>
                        </div>
                      )}
                      <CopyField label={t("Webhook / callback URL")} value={ch.webhook_url} />
                      {ch.verify_token && <CopyField label={t("Verify token")} value={ch.verify_token} />}
                    </div>
                  )}

                  {ch.provider === "website" && (
                    <div className="mt-3 space-y-1">
                      <CopyField label={t("Embed code: paste before </body> on your website")} value={`<script src="${typeof window === "undefined" ? "" : window.location.origin}/widget.js" data-channel="${ch.id}" async></script>`} />
                      <p className="text-xs text-slate-500">{t("Works with any site: WordPress (Appearance → Theme File Editor or a \"header & footer scripts\" plugin), Shopify (theme.liquid), Wix / Webflow (custom code).")} <a className="text-brand-700 underline" href={`/widget/${ch.id}`} target="_blank" rel="noreferrer">{t("Preview the chat window")}</a></p>
                    </div>
                  )}

                  {canManage && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {meta?.uses_oauth && !ch.is_demo && (
                        <button className="btn-primary px-2.5 py-1.5" onClick={() => authorize(ch)} disabled={busy === ch.id}>
                          <ExternalLink size={14} /> {ch.authorized ? t("Re-authorize") : t("Authorize with Microsoft")}
                        </button>
                      )}
                      {!ch.is_demo && (
                        <button className="btn-secondary px-2.5 py-1.5" onClick={() => run(ch.id, () => Api.testChannel(ch.id), "Connection OK.")} disabled={busy === ch.id}>
                          <Zap size={14} /> {t("Test")}
                        </button>
                      )}
                      {!ch.is_demo && ch.receive_mode.includes("polling") && (
                        <button className="btn-secondary px-2.5 py-1.5" disabled={busy === ch.id}
                          onClick={() => run(ch.id, async () => {
                            const r = await Api.syncChannel(ch.id);
                            setNotice({ kind: r.channel.status === "error" ? "err" : "ok", text: r.channel.status === "error" ? r.channel.last_error : "Synced — {n} new message(s).", vars: { n: r.new_messages } });
                          })}>
                          <RefreshCw size={14} className={clsx(busy === ch.id && "animate-spin")} /> {t("Sync now")}
                        </button>
                      )}
                      {!ch.is_demo && meta && (
                        <button className="btn-secondary px-2.5 py-1.5" onClick={() => setEditing({ provider: meta, channel: ch })}>{t("Edit")}</button>
                      )}
                      <button className="btn-ghost px-2.5 py-1.5 text-red-600 hover:bg-red-50"
                        onClick={() => window.confirm(t("Remove {name}? All its conversations will be deleted.", { name: ch.name })) && run(ch.id, () => Api.deleteChannel(ch.id), "Channel removed.")}>
                        <Trash size={14} /> {t("Remove")}
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Available providers */}
        {canManage && (
          <>
            <h2 className="mb-3 mt-10 text-sm font-semibold uppercase tracking-wide text-slate-500">{t("Add a channel")}</h2>
            {metaCfg && (metaCfg.whatsapp.enabled || metaCfg.pages.enabled) && (
              <div className="mb-3">
                <FacebookConnect cfg={metaCfg} onDone={(text) => { reload(); setNotice({ kind: "ok", text }); }} />
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {providers.map((p) => (
                <button key={p.key} onClick={() => setEditing({ provider: p })}
                  className="card flex items-center gap-3 p-4 text-left transition hover:border-brand-500 hover:shadow">
                  <ProviderIcon provider={p.key} size="lg" />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">
                      {p.label} {p.beta && <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-slate-500">{t("beta")}</span>}
                    </p>
                    <p className="text-xs capitalize text-slate-500">{p.category} · {p.receive_mode}</p>
                  </div>
                  <Plus size={18} className="text-slate-400" />
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {editing && (
        <ChannelForm
          provider={editing.provider}
          channel={editing.channel}
          onClose={() => setEditing(null)}
          onSaved={(ch) => {
            setEditing(null);
            reload();
            if (ch.status === "error") setNotice({ kind: "err", text: "Saved, but the connection check failed: {error}", vars: { error: ch.last_error } });
            else if (ch.status === "pending") setNotice({ kind: "ok", text: "Saved. Now click 'Authorize' to finish connecting." });
            else setNotice({ kind: "ok", text: "{name} is connected.", vars: { name: ch.name } });
          }}
        />
      )}
    </div>
  );
}

function ChannelForm({ provider, channel, onClose, onSaved }: {
  provider: ProviderMeta; channel?: Channel; onClose: () => void; onSaved: (c: Channel) => void;
}) {
  const t = useT();
  const [name, setName] = useState(channel?.name ?? provider.label);
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of provider.fields) {
      const v = String(channel?.credentials_preview?.[f.name] ?? f.default ?? "");
      // Saved secrets start empty: typing replaces them, leaving the field empty keeps the saved value
      init[f.name] = f.secret && v === MASK ? "" : v;
    }
    return init;
  });
  const hasSaved = (field: string) => channel?.credentials_preview?.[field] === MASK;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      // Empty secret on edit = keep the saved one
      const creds = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === "" && hasSaved(k) ? MASK : v]));
      const saved = channel
        ? await Api.updateChannel(channel.id, { name, credentials: creds })
        : await Api.createChannel({ provider: provider.key, name, credentials: values });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className="scroll-thin max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
          <ProviderIcon provider={provider.key} size="md" />
          <h3 className="flex-1 font-semibold">{channel ? t("Edit {name}", { name: channel.name }) : t("Connect {name}", { name: provider.label })}</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label={t("Close")}><X size={20} /></button>
        </div>
        <form onSubmit={save} className="space-y-4 px-5 py-4">
          {provider.setup_steps.length > 0 && (
            <ol className="list-decimal space-y-1 rounded-lg bg-slate-50 py-3 pl-8 pr-4 text-xs text-slate-600">
              {provider.setup_steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          )}
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">{t("Display name")}</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          {provider.fields.map((f) => (
            <label key={f.name} className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {f.label} {!f.required && <span className="font-normal text-slate-400">({t("Optional")})</span>}
              </span>
              {f.type === "select" ? (
                <select className="input" value={values[f.name]} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                  {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  className="input font-mono"
                  type={f.secret ? "password" : f.type === "number" ? "number" : "text"}
                  value={values[f.name]}
                  required={f.required && !hasSaved(f.name)}
                  autoComplete="off"
                  placeholder={hasSaved(f.name) ? t("Saved. Paste a new value to replace it") : ""}
                  onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                />
              )}
              {f.secret && hasSaved(f.name) && (
                <span className="mt-1 block text-xs font-medium text-emerald-700">
                  {values[f.name] ? t("Will be replaced when you save.") : t("A value is saved. Leave empty to keep it.")}
                </span>
              )}
              {f.help && <span className="mt-1 block text-xs text-slate-500">{f.help}</span>}
            </label>
          ))}
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{t(error)}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-secondary" onClick={onClose}>{t("Cancel")}</button>
            <button className="btn-primary" disabled={saving}>
              {saving && <LoaderCircle className="animate-spin" size={16} />} {channel ? t("Save") : t("Connect")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
