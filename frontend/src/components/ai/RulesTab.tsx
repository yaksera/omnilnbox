"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { CircleAlert, Hand, KeyRound, LoaderCircle, MessageCircleReply, Moon, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { Api } from "@/lib/api";
import type { AutomationRule, Channel, Member, RuleInput, RuleTrigger, Tag } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { UpgradeHint } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const TRIGGERS: Record<RuleTrigger, { label: string; help: string; icon: typeof Hand }> = {
  comment: { label: "Comment → DM", help: "Someone comments on your Facebook or Instagram post: send them a private message (and optionally reply publicly).", icon: MessageCircleReply },
  keyword: { label: "Keyword reply", help: "A message contains a word like \"price\" or \"kati\": send an instant reply, add a tag or assign it.", icon: KeyRound },
  welcome: { label: "Welcome message", help: "Greet every new contact the first time they message you.", icon: Hand },
  away: { label: "Away message", help: "Reply outside business hours (at most once every 12 hours per customer). Skipped when the AI chatbot is answering.", icon: Moon },
};

const TEMPLATES: Array<{ label: string; rule: RuleInput }> = [
  { label: "Price comments → DM", rule: { trigger: "comment", name: "Price comments → DM", keywords: ["price", "kati", "rate", "how much", "details", "dm"], reply_text: "Namaste {name}! 🙏 Thanks for your interest. Here are the details: ...", public_reply_text: "Hi {name}, we've sent you the details in your inbox 📩" } },
  { label: "Price question", rule: { trigger: "keyword", name: "Price question", keywords: ["price", "kati", "rate", "cost"], use_ai: true, reply_text: "Hi {name}! Our latest prices: ..." } },
  { label: "Welcome", rule: { trigger: "welcome", name: "Welcome", reply_text: "Namaste {name}! 🙏 Thanks for messaging us. How can we help you today?" } },
  { label: "Away", rule: { trigger: "away", name: "Away message", reply_text: "Thanks for your message! We're closed right now and will reply as soon as we open (10am-6pm, Sun-Fri)." } },
];

type Draft = RuleInput & { id: string | null };

export default function RulesTab({ canEdit, enabled, aiEnabled }: { canEdit: boolean; enabled: boolean; aiEnabled: boolean }) {
  const t = useT();
  const [rules, setRules] = useState<AutomationRule[] | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [kw, setKw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => Api.rules().then(setRules).catch(() => setRules([]));
  useEffect(() => {
    load();
    Api.channels().then(setChannels).catch(() => {});
    Api.tags().then(setTags).catch(() => {});
    if (canEdit) Api.team().then((team) => setMembers(team.members)).catch(() => {});
  }, [canEdit]);

  const pageChannels = channels.filter((c) => (c.provider === "messenger" || c.provider === "instagram") && !c.is_demo);

  function open(r: AutomationRule | null, template?: RuleInput) {
    setError(""); setKw("");
    if (r) {
      setDraft({ id: r.id, name: r.name, enabled: r.enabled, trigger: r.trigger, channel_id: r.channel?.id ?? null, keywords: r.keywords,
        match: r.match, post_id: r.post_id, reply_text: r.reply_text, use_ai: r.use_ai, public_reply_text: r.public_reply_text,
        add_tag_id: r.add_tag_id, assign_to_id: r.assign_to_id });
    } else {
      const tpl = template ?? TEMPLATES[0].rule;
      setDraft({ id: null, enabled: true, match: "contains", keywords: [], post_id: "", public_reply_text: "", use_ai: false,
        add_tag_id: null, assign_to_id: null, channel_id: tpl.trigger === "comment" ? pageChannels[0]?.id ?? null : null, ...tpl });
    }
  }

  async function save() {
    if (!draft) return;
    setBusy(true); setError("");
    const { id, ...body } = draft;
    const words = kw.trim() ? [...(body.keywords ?? []), ...kw.split(",").map((k) => k.trim()).filter(Boolean)] : body.keywords;
    try {
      await Api.saveRule(id, { ...body, keywords: words });
      setDraft(null); load();
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/channel_id: |reply_text: |keywords: /g, "") : t("Couldn't save"));
    } finally { setBusy(false); }
  }

  async function toggle(r: AutomationRule) {
    await Api.saveRule(r.id, { enabled: !r.enabled }); load();
  }
  async function remove(r: AutomationRule) {
    if (!window.confirm(t("Delete “{title}”?", { title: r.name }))) return;
    await Api.deleteRule(r.id); load();
  }

  if (!enabled) return <UpgradeHint feature={t("Automations")}>{t("Auto-replies, welcome and away messages, and comment-to-DM are included from the Starter plan.")}</UpgradeHint>;
  if (!rules) return <LoaderCircle className="animate-spin text-slate-400" />;

  const addKeywords = (value: string) => {
    const parts = value.split(",").map((k) => k.trim()).filter(Boolean);
    if (draft && parts.length) setDraft({ ...draft, keywords: Array.from(new Set([...(draft.keywords ?? []), ...parts])) });
    setKw("");
  };

  return (
    <div className="space-y-5">
      {canEdit && !draft && (
        <div className="card p-4">
          <p className="text-sm font-semibold">{t("Start from a template")}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {TEMPLATES.map((tpl) => {
              const Icon = TRIGGERS[tpl.rule.trigger!].icon;
              return (
                <button key={tpl.label} type="button" onClick={() => open(null, tpl.rule)}
                  className="flex items-start gap-2 rounded-xl border border-slate-200 p-3 text-left hover:border-brand-400 hover:bg-brand-50/40">
                  <Icon size={18} className="mt-0.5 shrink-0 text-brand-600" />
                  <span><span className="block text-sm font-medium">{t(tpl.label)}</span><span className="line-clamp-2 text-xs text-slate-500">{t(TRIGGERS[tpl.rule.trigger!].help)}</span></span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {draft && (
        <div className="card space-y-4 border-brand-300 p-5">
          <div className="flex flex-wrap gap-2">
            {(Object.keys(TRIGGERS) as RuleTrigger[]).map((trig) => {
              const Icon = TRIGGERS[trig].icon;
              return (
                <button key={trig} type="button" onClick={() => setDraft({ ...draft, trigger: trig, channel_id: trig === "comment" ? draft.channel_id ?? pageChannels[0]?.id ?? null : draft.channel_id })}
                  className={clsx("flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm", draft.trigger === trig ? "border-brand-500 bg-brand-50 text-brand-800" : "border-slate-200 text-slate-600")}>
                  <Icon size={14} /> {t(TRIGGERS[trig].label)}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-slate-500">{t(TRIGGERS[draft.trigger!].help)}</p>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">{t("Name")}
              <input className="input mt-1" maxLength={120} value={draft.name ?? ""} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </label>
            <label className="text-sm">{draft.trigger === "comment" ? t("Facebook Page / Instagram account") : t("Channel")}
              <select className="input mt-1" value={draft.channel_id ?? ""} onChange={(e) => setDraft({ ...draft, channel_id: e.target.value || null })}>
                {draft.trigger !== "comment" && <option value="">{t("All channels")}</option>}
                {(draft.trigger === "comment" ? pageChannels : channels).map((c) => <option key={c.id} value={c.id}>{c.name}{c.is_demo ? ` (${t("demo")})` : ""}</option>)}
              </select>
              {draft.trigger === "comment" && pageChannels.length === 0 && (
                <span className="mt-1 flex gap-1 text-xs text-amber-700"><CircleAlert size={12} className="mt-0.5" /> {t("Connect a Messenger (Facebook Page) or Instagram channel first.")}</span>
              )}
            </label>
          </div>

          {(draft.trigger === "keyword" || draft.trigger === "comment") && (
            <div>
              <p className="text-sm">{t("Keywords")} {draft.trigger === "comment" && <span className="text-slate-500">{t("(leave empty to answer every comment)")}</span>}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-300 p-1.5">
                {(draft.keywords ?? []).map((k) => (
                  <span key={k} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs">
                    {k}<button type="button" aria-label={t("Remove {word}", { word: k })} onClick={() => setDraft({ ...draft, keywords: draft.keywords!.filter((x) => x !== k) })}><X size={12} /></button>
                  </span>
                ))}
                <input className="min-w-[160px] flex-1 border-0 px-1 py-0.5 text-sm outline-none" placeholder={t("Type a word and press Enter (e.g. price, kati)")} value={kw}
                  onChange={(e) => setKw(e.target.value)} onBlur={() => addKeywords(kw)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addKeywords(kw); } }} />
              </div>
              {draft.trigger === "keyword" && (
                <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                  <input type="checkbox" className="accent-brand-600" checked={draft.match === "exact"} onChange={(e) => setDraft({ ...draft, match: e.target.checked ? "exact" : "contains" })} />
                  {t("Only when the whole message is exactly one of the keywords")}
                </label>
              )}
            </div>
          )}

          {draft.trigger === "comment" && (
            <label className="block text-sm">{t("Only this post (optional)")}
              <input className="input mt-1" placeholder={t("Post ID, e.g. 123456789012345. Empty = all posts")} value={draft.post_id ?? ""} maxLength={100}
                onChange={(e) => setDraft({ ...draft, post_id: e.target.value.trim() })} />
            </label>
          )}

          <label className="block text-sm">{draft.trigger === "comment" ? t("Private message (DM) to the commenter") : t("Reply")}
            <textarea className="input mt-1 min-h-[90px]" maxLength={2000} value={draft.reply_text ?? ""} onChange={(e) => setDraft({ ...draft, reply_text: e.target.value })}
              placeholder={t("Use {name} for the customer's first name", { name: "{name}" })} />
          </label>
          {draft.trigger !== "welcome" && draft.trigger !== "away" && (
            <label className={clsx("flex items-start gap-2 text-sm", !aiEnabled && "opacity-50")}>
              <input type="checkbox" className="mt-1 accent-brand-600" disabled={!aiEnabled} checked={!!draft.use_ai} onChange={(e) => setDraft({ ...draft, use_ai: e.target.checked })} />
              <span><Sparkles size={14} className="mr-1 inline text-brand-600" /><b>{t("Let AI write the answer")}</b> {t("from your knowledge base, in the customer's language. The text above is used if the AI isn't available. 1 credit each.")}</span>
            </label>
          )}
          {draft.trigger === "comment" && (
            <label className="block text-sm">{t("Public reply under the comment (optional)")}
              <input className="input mt-1" maxLength={500} value={draft.public_reply_text ?? ""} placeholder={t("e.g. Hi {name}, check your inbox 📩", { name: "{name}" })} onChange={(e) => setDraft({ ...draft, public_reply_text: e.target.value })} />
            </label>
          )}
          {draft.trigger === "keyword" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm">{t("Add tag")}
                <select className="input mt-1" value={draft.add_tag_id ?? ""} onChange={(e) => setDraft({ ...draft, add_tag_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">{t("No tag")}</option>
                  {tags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
                </select>
              </label>
              <label className="text-sm">{t("Assign to")}
                <select className="input mt-1" value={draft.assign_to_id ?? ""} onChange={(e) => setDraft({ ...draft, assign_to_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">{t("Nobody")}</option>
                  {members.map((m) => <option key={m.id} value={m.id}>{m.name || m.email}</option>)}
                </select>
              </label>
            </div>
          )}
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <div className="flex gap-2">
            <button type="button" className="btn-primary" disabled={busy || !draft.name?.trim()} onClick={save}>{busy && <LoaderCircle className="animate-spin" size={16} />} {draft.id ? t("Save") : t("Create automation")}</button>
            <button type="button" className="btn-ghost" onClick={() => setDraft(null)}><X size={16} /> {t("Cancel")}</button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">{t("Your automations ({n})", { n: rules.length })}</p>
        {canEdit && !draft && <button type="button" className="btn-secondary" onClick={() => open(null, { trigger: "keyword", name: "" })}><Plus size={16} /> {t("New")}</button>}
      </div>
      {rules.length === 0 ? <p className="card p-6 text-center text-sm text-slate-500">{t("No automations yet. Pick a template above.")}</p> : (
        <div className="card divide-y divide-slate-100">
          {rules.map((r) => {
            const T = TRIGGERS[r.trigger];
            return (
              <div key={r.id} className="flex flex-wrap items-center gap-3 p-4">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><T.icon size={18} /></span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                    {r.name}
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-normal text-slate-600">{t(T.label)}</span>
                    {r.use_ai && <span className="inline-flex items-center gap-0.5 rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-normal text-brand-700"><Sparkles size={10} /> AI</span>}
                    {r.channel && <span className="inline-flex items-center gap-1 text-xs font-normal text-slate-500"><ProviderIcon provider={r.channel.provider} size="xs" /> {r.channel.name}</span>}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    {r.keywords.length > 0 && <>{t("When: {words}", { words: r.keywords.slice(0, 6).join(", ") + (r.keywords.length > 6 ? "…" : "") })} · </>}
                    {r.run_count === 1 ? t("Ran {n} time", { n: r.run_count }) : t("Ran {n} times", { n: r.run_count })}{r.last_run_at ? t(", last {when}", { when: new Date(r.last_run_at).toLocaleString() }) : ""}
                  </p>
                  {r.last_error && <p className="mt-0.5 line-clamp-2 text-xs text-red-700">{t("Last error: {error}", { error: r.last_error })}</p>}
                </div>
                {canEdit && (
                  <div className="flex items-center gap-1">
                    <button type="button" role="switch" aria-checked={r.enabled} aria-label={r.enabled ? t("Turn off {name}", { name: r.name }) : t("Turn on {name}", { name: r.name })} onClick={() => toggle(r)}
                      className={clsx("relative h-5 w-9 rounded-full transition", r.enabled ? "bg-brand-600" : "bg-slate-300")}>
                      <span className={clsx("absolute top-0.5 h-4 w-4 rounded-full bg-white transition", r.enabled ? "left-[18px]" : "left-0.5")} />
                    </button>
                    <button type="button" className="btn-ghost px-2" aria-label={t("Edit")} onClick={() => open(r)}><Pencil size={15} /></button>
                    <button type="button" className="btn-ghost px-2 text-red-600" aria-label={t("Delete")} onClick={() => remove(r)}><Trash2 size={15} /></button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <p className="text-xs text-slate-500">{t("Comment → DM: Meta allows one private message per comment, within 7 days. New comments are picked up instantly by webhook (subscribe your app to the Page “feed” and Instagram “comments” fields), and every worker cycle as a fallback.")}</p>
    </div>
  );
}
