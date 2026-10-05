"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { CircleAlert, LoaderCircle, Megaphone, Plus, Send, Trash2, Users, X } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import type { Broadcast, BroadcastAudience, Channel, Tag, WhatsAppTemplate } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { UpgradeHint, useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const SUPPORTED = ["whatsapp", "telegram", "viber", "messenger", "instagram"];
const STATUS: Record<Broadcast["status"], string> = { draft: "Draft", sending: "Sending…", done: "Sent", cancelled: "Cancelled" };

function Composer({ channels, tags, onDone, onClose }: { channels: Channel[]; tags: Tag[]; onDone: (b: Broadcast) => void; onClose: () => void }) {
  const t = useT();
  const [channelId, setChannelId] = useState(channels[0]?.id ?? "");
  const channel = channels.find((c) => c.id === channelId);
  const isWA = channel?.provider === "whatsapp";
  const [name, setName] = useState("");
  const [text, setText] = useState("Namaste {name}! 🎉 ");
  const [templates, setTemplates] = useState<WhatsAppTemplate[] | null>(null);
  const [tpl, setTpl] = useState<WhatsAppTemplate | null>(null);
  const [vars, setVars] = useState<string[]>([]);
  const [audience, setAudience] = useState<BroadcastAudience>({ tags: [], active_days: null, customers_only: false });
  const [info, setInfo] = useState<{ count: number; sample: string[]; note: string; opted_out: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setTemplates(null); setTpl(null); setError("");
    if (isWA && channelId) Api.whatsappTemplates(channelId).then(setTemplates).catch((e) => { setTemplates([]); setError(e.message); });
  }, [channelId, isWA]);
  useEffect(() => {
    if (!channelId) return;
    const timer = setTimeout(() => Api.broadcastAudience(channelId, audience).then(setInfo).catch(() => setInfo(null)), 250);
    return () => clearTimeout(timer);
  }, [channelId, audience]);

  const preview = useMemo(() => {
    if (isWA) return (tpl?.body ?? "").replace(/\{\{(\d+)\}\}/g, (m, n) => (vars[Number(n) - 1] || m).replace("{name}", "Anita"));
    return text.replace(/\{name\}/g, "Anita");
  }, [isWA, tpl, vars, text]);

  async function create(send: boolean) {
    setBusy(true); setError("");
    try {
      const b = await Api.createBroadcast({
        name: name || (isWA ? tpl?.name : text.slice(0, 40)) || "Broadcast", channel_id: channelId, kind: isWA ? "template" : "text", text,
        template_name: tpl?.name ?? "", template_language: tpl?.language ?? "", template_body: tpl?.body ?? "", variables: vars, audience,
      });
      if (send) {
        if (!window.confirm(t("Send to {n} people now? This can't be undone.", { n: info?.count ?? 0 }))) { onDone(b); return; }
        onDone(await Api.broadcastAction(b.id, "send"));
      } else onDone(b);
    } catch (err) { setError(err instanceof Error ? err.message.replace(/^\w+: /, "") : t("Failed")); setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true">
      <div className="card grid max-h-[92vh] w-full max-w-4xl overflow-y-auto md:grid-cols-[1fr_300px]">
        <div className="space-y-4 p-5">
          <div className="flex items-center justify-between"><h2 className="flex items-center gap-2 font-semibold"><Megaphone size={18} /> {t("New broadcast")}</h2>
            <button type="button" className="btn-ghost px-2 md:hidden" onClick={onClose} aria-label={t("Close")}><X size={16} /></button></div>
          <label className="block text-sm">{t("Name (only for you)")}<input className="input mt-1" placeholder={t("e.g. Dashain sale 2026")} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} /></label>
          <div>
            <p className="text-sm">{t("Send from")}</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {channels.map((c) => (
                <button key={c.id} type="button" onClick={() => setChannelId(c.id)}
                  className={clsx("flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-sm", c.id === channelId ? "border-brand-500 bg-brand-50" : "border-slate-200")}>
                  <ProviderIcon provider={c.provider} size="sm" className="rounded-full" /> {c.name}{c.is_demo && ` (${t("demo")})`}
                </button>
              ))}
            </div>
          </div>
          {isWA ? (
            <div className="space-y-2">
              <label className="block text-sm">{t("Approved WhatsApp template")}
                <select className="input mt-1" value={tpl ? `${tpl.name}|${tpl.language}` : ""} onChange={(e) => { const found = templates?.find((x) => `${x.name}|${x.language}` === e.target.value) ?? null; setTpl(found); setVars(Array.from({ length: found?.variables ?? 0 }, (_, i) => (i === 0 ? "{name}" : ""))); }}>
                  <option value="">{templates === null ? t("Loading…") : templates.length ? t("Choose a template") : t("No approved templates")}</option>
                  {templates?.map((x) => <option key={`${x.name}|${x.language}`} value={`${x.name}|${x.language}`}>{x.name} ({x.language}, {x.category.toLowerCase()})</option>)}
                </select>
              </label>
              <p className="text-xs text-slate-500">{t("Create templates in WhatsApp Manager → Message templates. Meta reviews them (usually within minutes).")}</p>
              {vars.map((v, i) => (
                <label key={i} className="block text-sm">{`{{${i + 1}}}`}<input className="input mt-1" value={v} placeholder={i === 0 ? "{name}" : t("e.g. 20%")} onChange={(e) => setVars(vars.map((x, j) => (j === i ? e.target.value : x)))} /></label>
              ))}
            </div>
          ) : (
            <label className="block text-sm">{t("Message")}<textarea className="input mt-1 min-h-[120px]" maxLength={4000} value={text} onChange={(e) => setText(e.target.value)} />
              <span className="text-xs text-slate-500">{t("{name} becomes each customer's first name. Keep it useful: offers, restocks, order updates.", { name: "{name}" })}</span></label>
          )}
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="flex items-center gap-2 text-sm font-medium"><Users size={15} /> {t("Who gets it")}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {tags.map((tag) => {
                const on = audience.tags?.includes(tag.id);
                return <button key={tag.id} type="button" onClick={() => setAudience({ ...audience, tags: on ? audience.tags!.filter((x) => x !== tag.id) : [...(audience.tags ?? []), tag.id] })}
                  className={clsx("rounded-full px-2.5 py-0.5 text-xs font-medium", on ? "text-white" : "bg-slate-100 text-slate-600")} style={on ? { background: tag.color } : undefined}>{tag.name}</button>;
              })}
              {tags.length === 0 && <span className="text-xs text-slate-500">{t("Everyone who has chatted on this channel. Add tags to target groups (VIP, Pokhara…).")}</span>}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
              <label className="flex items-center gap-2">{t("Active in the last")}
                <select className="input w-32 py-1" value={audience.active_days ?? ""} onChange={(e) => setAudience({ ...audience, active_days: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">{t("any time")}</option><option value="7">{t("{n} days", { n: 7 })}</option><option value="30">{t("{n} days", { n: 30 })}</option><option value="90">{t("{n} days", { n: 90 })}</option>
                </select></label>
              <label className="flex items-center gap-2"><input type="checkbox" className="accent-brand-600" checked={!!audience.customers_only} onChange={(e) => setAudience({ ...audience, customers_only: e.target.checked })} /> {t("Only customers with a profile")}</label>
            </div>
            {info && <p className="mt-3 text-sm"><b>{info.count}</b> {info.count === 1 ? t("person") : t("people")}{info.sample.length > 0 && <span className="text-slate-500"> ({info.sample.join(", ")}{info.count > info.sample.length ? "…" : ""})</span>}. {info.opted_out > 0 && <span className="text-slate-500">{t("{n} unsubscribed (replied STOP) are left out.", { n: info.opted_out })}</span>}</p>}
            {info?.note && <p className="mt-1 flex gap-1 text-xs text-amber-800"><CircleAlert size={13} className="mt-0.5 shrink-0" /> {info.note}</p>}
          </div>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primary" disabled={busy || !channelId || (isWA ? !tpl : !text.trim()) || !info?.count} onClick={() => create(true)}>
              {busy ? <LoaderCircle className="animate-spin" size={15} /> : <Send size={15} />} {t("Send now")}
            </button>
            <button type="button" className="btn-secondary" disabled={busy || !channelId} onClick={() => create(false)}>{t("Save draft")}</button>
            <button type="button" className="btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          </div>
        </div>
        <div className="bg-slate-100 p-5">
          <p className="text-xs font-medium uppercase text-slate-500">{t("Preview")}</p>
          <div className="mt-3 rounded-2xl bg-[#e5ddd5] p-3">
            <div className="max-w-[90%] whitespace-pre-wrap break-words rounded-lg rounded-tl-none bg-white px-3 py-2 text-sm shadow-sm">{preview || <span className="text-slate-400">{t("Your message…")}</span>}</div>
          </div>
          <p className="mt-3 text-xs text-slate-500">{t("Replies come back to your inbox like normal chats. Anyone who replies STOP is unsubscribed automatically.")}</p>
        </div>
      </div>
    </div>
  );
}

export default function BroadcastsPage() {
  const t = useT();
  const { can } = useMe();
  const [list, setList] = useState<Broadcast[] | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [composing, setComposing] = useState(false);
  const [locked, setLocked] = useState(false);

  const load = () => Api.broadcasts().then(setList).catch((e) => { if (e instanceof ApiError && e.status === 402) setLocked(true); });
  useEffect(() => {
    load();
    Api.channels().then((c) => setChannels(c.filter((x) => SUPPORTED.includes(x.provider)))).catch(() => undefined);
    Api.tags().then(setTags).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!list?.some((b) => b.status === "sending")) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [list]);

  if (locked) return <div className="mx-auto max-w-2xl p-6"><UpgradeHint feature={t("Broadcasts")}>{t("Send offers and updates to your WhatsApp, Telegram, Viber and Messenger contacts on the Pro plan and above.")}</UpgradeHint></div>;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <div><h1 className="text-xl font-bold">{t("Broadcasts")}</h1>
            <p className="text-sm text-slate-500">{t("Send one message to many customers: offers, restock alerts, festival wishes.")}</p></div>
          {can("send_broadcasts") && <button type="button" className="btn-primary ml-auto" disabled={!channels.length} onClick={() => setComposing(true)}><Plus size={16} /> {t("New broadcast")}</button>}
        </div>
        {!channels.length && <p className="card mt-5 p-4 text-sm text-slate-600">{t("Connect WhatsApp, Telegram, Viber, Messenger or Instagram first. Broadcasts go to people who have chatted with you there.")}</p>}
        <div className="mt-5 space-y-3">
          {list === null ? <LoaderCircle className="animate-spin text-slate-400" /> : list.length === 0 ? (
            <div className="card p-10 text-center"><Megaphone className="mx-auto text-slate-300" size={36} /><p className="mt-2 font-medium">{t("No broadcasts yet")}</p></div>
          ) : list.map((b) => {
            const pct = b.total ? Math.round(((b.sent + b.failed) / b.total) * 100) : 0;
            return (
              <div key={b.id} className="card p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <ProviderIcon provider={b.channel.provider} size="md" />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{b.name}</p>
                    <p className="text-xs text-slate-500">{b.channel.name} · {t(STATUS[b.status])}{b.started_at && ` · ${new Date(b.started_at).toLocaleString()}`}{b.created_by && ` · ${t("by {name}", { name: b.created_by })}`}</p>
                  </div>
                  {b.status !== "draft" && <p className="text-sm"><b>{b.sent}</b> {t("sent")}{b.failed > 0 && <span className="text-red-600"> · {t("{n} failed", { n: b.failed })}</span>} <span className="text-slate-400">{t("of {total}", { total: b.total })}</span></p>}
                  {b.status === "draft" && can("send_broadcasts") && (
                    <>
                      <button type="button" className="btn-primary px-3 py-1.5" onClick={async () => { if (window.confirm(t("Send this broadcast now?"))) { await Api.broadcastAction(b.id, "send"); load(); } }}><Send size={14} /> {t("Send")}</button>
                      <button type="button" className="btn-ghost px-2 text-red-600" aria-label={t("Delete draft")} onClick={async () => { await Api.deleteBroadcast(b.id); load(); }}><Trash2 size={15} /></button>
                    </>
                  )}
                  {b.status === "sending" && can("send_broadcasts") && <button type="button" className="btn-secondary px-3 py-1.5" onClick={async () => { await Api.broadcastAction(b.id, "cancel"); load(); }}>{t("Stop")}</button>}
                </div>
                {b.status !== "draft" && <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className={clsx("h-full", b.failed ? "bg-amber-500" : "bg-emerald-500")} style={{ width: `${pct}%` }} /></div>}
                <p className="mt-2 line-clamp-2 whitespace-pre-wrap text-sm text-slate-600">{b.kind === "template" ? b.template_body || t("Template: {name}", { name: b.template_name }) : b.text}</p>
              </div>
            );
          })}
        </div>
      </div>
      {composing && <Composer channels={channels} tags={tags} onClose={() => setComposing(false)} onDone={() => { setComposing(false); load(); }} />}
    </div>
  );
}
