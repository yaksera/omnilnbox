"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, CircleCheck, Code2, History, Plus, Store, Trash } from "lucide-react";
import SecuritySection from "@/components/settings/SecuritySection";
import SessionsSection from "@/components/settings/SessionsSection";
import NotificationsSection from "@/components/settings/NotificationsSection";
import { BrandingSection, QualitySection } from "@/components/settings/QualitySection";
import { Api } from "@/lib/api";
import type { CannedReply, Tag } from "@/lib/types";
import { UpgradeHint, useMe } from "@/components/AppShell";
import { useLang, useT, type Lang } from "@/lib/i18n";

const TAG_COLORS = ["#6366f1", "#0ea5e9", "#14b8a6", "#22c55e", "#eab308", "#f97316", "#ef4444", "#ec4899", "#64748b"];

function Section({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <section className="card p-5">
      <h2 className="font-semibold">{title}</h2>
      {desc && <p className="mt-1 text-sm text-slate-600">{desc}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Saved({ show }: { show: boolean }) {
  const t = useT();
  return show ? <span className="inline-flex items-center gap-1 text-sm text-emerald-700"><CircleCheck size={15} /> {t("Saved")}</span> : null;
}

const LANGS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ne", label: "नेपाली" },
];

function LanguageSection() {
  const t = useT();
  const { lang, setLang } = useLang();
  return (
    <section id="language" className="card p-5">
      <h2 className="font-semibold">{t("Language")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t("Choose the language of the OmniInbox app. Messages to your customers are not translated.")}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {LANGS.map((l) => (
          <button key={l.value} type="button" aria-pressed={lang === l.value}
            className={lang === l.value ? "btn-primary" : "btn-secondary"}
            onClick={() => { setLang(l.value); Api.setLanguage(l.value).catch(() => undefined); }}>
            {l.label}
          </button>
        ))}
      </div>
    </section>
  );
}

export default function SettingsPage() {
  const t = useT();
  const { me, reloadMe, can, hasFeature } = useMe();
  const [wsName, setWsName] = useState(me.workspace.name);
  const [name, setName] = useState(me.user.name);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [tags, setTags] = useState<Tag[]>([]);
  const [canned, setCanned] = useState<CannedReply[]>([]);
  const [newTag, setNewTag] = useState({ name: "", color: TAG_COLORS[0] });
  const [newCanned, setNewCanned] = useState({ shortcut: "", title: "", body: "" });

  useEffect(() => {
    Api.tags().then(setTags);
    Api.canned().then(setCanned);
  }, []);

  async function run(key: string, fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      setSaved(key);
      setTimeout(() => setSaved(""), 2000);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn’t save"));
      return false;
    }
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold">{t("Settings")}</h1>
        {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

        <LanguageSection />

        {can("manage_settings") && (
          <Section title={t("Workspace")}>
            <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); run("ws", async () => { await Api.updateWorkspace({ name: wsName }); await reloadMe(); }); }}>
              <input className="input" value={wsName} onChange={(e) => setWsName(e.target.value)} required maxLength={120} />
              <button className="btn-primary">{t("Save")}</button>
            </form>
            <Saved show={saved === "ws"} />
            <div className="mt-5 border-t border-slate-100 pt-4">
              <label className="flex items-start gap-3">
                <input type="checkbox" className="mt-1 h-4 w-4 accent-brand-600" disabled={!hasFeature("agent_visibility")}
                  checked={!me.workspace.agents_see_all}
                  onChange={(e) => run("vis", async () => { await Api.updateWorkspace({ agents_see_all: !e.target.checked }); await reloadMe(); })} />
                <span>
                  <span className="block text-sm font-medium">{t("Agents only see their own and unassigned conversations")}</span>
                  <span className="block text-xs text-slate-500">{t("Supervisors, admins and the owner always see everything.")}{!hasFeature("agent_visibility") && ` ${t("Available on Business.")}`}</span>
                </span>
              </label>
              <Saved show={saved === "vis"} />
            </div>
          </Section>
        )}

        <Section title={t("Your profile")}>
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); run("name", async () => { await Api.updateMe({ name }); await reloadMe(); }); }}>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={150} />
            <button className="btn-primary">{t("Save")}</button>
          </form>
          <Saved show={saved === "name"} />
          <form className="mt-5 grid gap-2 border-t border-slate-100 pt-4 sm:grid-cols-[1fr_1fr_auto]"
            onSubmit={(e) => { e.preventDefault(); run("pw", async () => { await Api.updateMe(pw); setPw({ current_password: "", new_password: "" }); }); }}>
            <input className="input" type="password" placeholder={t("Current password")} required value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} autoComplete="current-password" />
            <input className="input" type="password" placeholder={t("New password")} required minLength={8} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} autoComplete="new-password" />
            <button className="btn-secondary">{t("Change password")}</button>
          </form>
          <Saved show={saved === "pw"} />
        </Section>

        <NotificationsSection />
        <SecuritySection />
        <SessionsSection />
        {can("manage_settings") && <QualitySection />}
        {can("manage_settings") && <BrandingSection />}
        {[
          can("manage_shop") && { href: "/settings/shop", icon: Store, title: t("Shop settings"), text: t("Khalti / eSewa payments, Nepal Can Move / Pathao, delivery charges and order messages.") },
          can("manage_developers") && { href: "/settings/developers", icon: Code2, title: t("API & webhooks"), text: t("API keys and webhooks to connect your website, ERP, Google Sheets or Zapier.") },
        ].filter(Boolean).map((l) => { const x = l as { href: string; icon: typeof Store; title: string; text: string }; return (
          <Link key={x.href} href={x.href} className="card flex items-center gap-3 p-5 hover:border-brand-300">
            <x.icon size={18} className="text-slate-500" />
            <span className="flex-1"><span className="block font-semibold">{x.title}</span><span className="block text-sm text-slate-600">{x.text}</span></span>
            <ChevronRight size={18} className="text-slate-400" />
          </Link>
        ); })}
        {can("view_audit_log") && (
          <Link href="/settings/activity" className="card flex items-center gap-3 p-5 hover:border-brand-300">
            <History size={18} className="text-slate-500" />
            <span className="flex-1"><span className="block font-semibold">{t("Activity log")}</span><span className="block text-sm text-slate-600">{t("Logins, team changes, channels, billing and automations. Who did what, and when.")}</span></span>
            <ChevronRight size={18} className="text-slate-400" />
          </Link>
        )}

        <Section title={t("Tags")} desc={t("Label conversations (VIP, order issue, lead…) and filter the inbox by them.")}>
          {!hasFeature("tags") ? <UpgradeHint feature={t("Tags")}>{t("Organise conversations with tags on Starter and higher.")}</UpgradeHint> : (
            <>
              <div className="flex flex-wrap gap-2">
                {tags.length === 0 && <p className="text-sm text-slate-500">{t("No tags yet.")}</p>}
                {tags.map((tag) => (
                  <span key={tag.id} className="inline-flex items-center gap-1.5 rounded-full py-1 pl-2.5 pr-1.5 text-xs font-medium text-white" style={{ background: tag.color }}>
                    {tag.name}
                    {can("manage_tags") && (
                      <button onClick={() => run("tag", async () => { await Api.deleteTag(tag.id); setTags(tags.filter((x) => x.id !== tag.id)); })} aria-label={t("Delete {name}", { name: tag.name })} className="rounded-full p-0.5 hover:bg-black/20"><Trash size={11} /></button>
                    )}
                  </span>
                ))}
              </div>
              {can("manage_tags") && (
                <form className="mt-4 flex flex-wrap items-center gap-2" onSubmit={(e) => {
                  e.preventDefault();
                  run("tag", async () => { const created = await Api.createTag(newTag); setTags([...tags, created].sort((a, b) => a.name.localeCompare(b.name))); setNewTag({ ...newTag, name: "" }); });
                }}>
                  <input className="input w-44" placeholder={t("Tag name")} required maxLength={40} value={newTag.name} onChange={(e) => setNewTag({ ...newTag, name: e.target.value })} />
                  <div className="flex gap-1">
                    {TAG_COLORS.map((c) => (
                      <button type="button" key={c} onClick={() => setNewTag({ ...newTag, color: c })} aria-label={t("Colour {c}", { c })}
                        className={`h-6 w-6 rounded-full ${newTag.color === c ? "ring-2 ring-slate-900 ring-offset-2" : ""}`} style={{ background: c }} />
                    ))}
                  </div>
                  <button className="btn-secondary"><Plus size={16} /> {t("Add")}</button>
                </form>
              )}
            </>
          )}
        </Section>

        <Section title={t("Saved replies")} desc={t("Type / in the reply box to insert one. Use them for greetings, prices, delivery info and FAQs.")}>
          {!hasFeature("canned_replies") ? <UpgradeHint feature={t("Saved replies")}>{t("Reply faster with saved replies on Starter and higher.")}</UpgradeHint> : (
            <>
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                {canned.length === 0 && <li className="p-3 text-sm text-slate-500">{t("No saved replies yet.")}</li>}
                {canned.map((c) => (
                  <li key={c.id} className="flex gap-3 p-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium"><span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">/{c.shortcut}</span> {c.title}</p>
                      <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-sm text-slate-600">{c.body}</p>
                    </div>
                    {can("manage_canned") && (
                      <button className="btn-ghost px-2 text-red-600 hover:bg-red-50" aria-label={t("Delete saved reply")}
                        onClick={() => run("canned", async () => { await Api.deleteCanned(c.id); setCanned(canned.filter((x) => x.id !== c.id)); })}><Trash size={15} /></button>
                    )}
                  </li>
                ))}
              </ul>
              {can("manage_canned") && (
                <form className="mt-4 space-y-2" onSubmit={(e) => {
                  e.preventDefault();
                  run("canned", async () => { const c = await Api.createCanned(newCanned); setCanned([...canned, c]); setNewCanned({ shortcut: "", title: "", body: "" }); });
                }}>
                  <div className="grid gap-2 sm:grid-cols-[160px_1fr]">
                    <input className="input font-mono" placeholder={t("shortcut")} required pattern="[a-z0-9_\-]+" title={t("lowercase letters, numbers, - and _")}
                      value={newCanned.shortcut} onChange={(e) => setNewCanned({ ...newCanned, shortcut: e.target.value.toLowerCase() })} />
                    <input className="input" placeholder={t("Title (e.g. Delivery info)")} required value={newCanned.title} onChange={(e) => setNewCanned({ ...newCanned, title: e.target.value })} />
                  </div>
                  <textarea className="input min-h-[80px]" placeholder={t("Reply text")} required maxLength={4000} value={newCanned.body} onChange={(e) => setNewCanned({ ...newCanned, body: e.target.value })} />
                  <button className="btn-secondary"><Plus size={16} /> {t("Add saved reply")}</button>
                </form>
              )}
            </>
          )}
          <Saved show={saved === "canned"} />
        </Section>
      </div>
    </div>
  );
}

