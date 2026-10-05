"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { ArrowRight, BookOpen, CircleCheck, Circle, LoaderCircle, PartyPopper } from "lucide-react";
import { Api } from "@/lib/api";
import type { Onboarding } from "@/lib/types";
import { useMe } from "@/components/AppShell";
import { enablePush } from "@/lib/notifications";
import { useT } from "@/lib/i18n";

const GUIDES: Record<string, string> = {
  connect_channel: "/docs/channels",
  business_info: "/docs/ai-assistant",
  knowledge: "/docs/knowledge-base",
  automation: "/docs/automations",
  invite_team: "/docs/team-and-roles",
  notifications: "/docs/notifications",
  first_reply: "/docs/inbox",
  verify_email: "/docs/getting-started",
};

export default function GetStartedPage() {
  const { me } = useMe();
  const t = useT();
  const [data, setData] = useState<Onboarding | null>(null);
  const [busy, setBusy] = useState("");
  // English text (translated when shown) plus placeholder values
  const [note, setNote] = useState<{ text: string; vars?: Record<string, string> } | null>(null);

  const load = () => Api.onboarding().then(setData).catch(() => undefined);
  useEffect(() => { load(); }, []);

  async function act(key: string) {
    setBusy(key); setNote(null);
    try {
      if (key === "verify_email") {
        const r = await Api.sendVerification();
        setNote(r.dev_link ? { text: "Development mode: open {link}", vars: { link: r.dev_link } } : { text: "Confirmation email sent. Check your inbox." });
      } else if (key === "notifications") {
        const r = await enablePush();
        setNote({ text: r === "on" ? "Notifications are on for this device." : r === "denied"
          ? "Your browser blocked notifications. Allow them in the site settings (lock icon in the address bar)."
          : "This browser doesn't support push notifications. On iPhone, first add OmniInbox to your Home Screen." });
        await load();
      }
    } finally { setBusy(""); }
  }

  if (!data) return <div className="flex h-full items-center justify-center"><LoaderCircle className="animate-spin text-slate-400" /></div>;
  const pct = Math.round((data.done / data.total) * 100);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl p-4 sm:p-8">
        <p className="text-sm text-slate-500">{t("Welcome, {name}", { name: me.user.name.split(" ")[0] })} 👋</p>
        <h1 className="mt-1 text-2xl font-bold">{t("Set up {name}", { name: me.workspace.name })}</h1>
        <p className="mt-1 text-sm text-slate-600">{t("Most shops finish this in about 15 minutes. Each step has a step-by-step guide with screenshots.")}</p>

        <div className="mt-5 flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-sm font-medium text-slate-700">{t("{done} of {total}", { done: data.done, total: data.total })}</span>
        </div>

        {data.done === data.total && (
          <div className="mt-5 flex items-center gap-3 rounded-xl bg-emerald-50 p-4 text-emerald-900">
            <PartyPopper size={24} /> <p className="text-sm"><b>{t("All set!")}</b> {t("Your inbox is ready. Explore orders, broadcasts and the help center to get even more out of OmniInbox.")}</p>
          </div>
        )}
        {note && <p className="mt-4 break-all rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">{t(note.text, note.vars)}</p>}

        <ol className="mt-6 space-y-3">
          {data.steps.map((s, i) => (
            <li key={s.key} className={clsx("card flex items-start gap-4 p-4", s.done && "opacity-70")}>
              <span className="mt-0.5">{s.done ? <CircleCheck className="text-emerald-600" size={22} /> : <Circle className="text-slate-300" size={22} />}</span>
              <div className="min-w-0 flex-1">
                <p className={clsx("font-medium", s.done && "line-through decoration-slate-400")}>{i + 1}. {t(s.title)}</p>
                <p className="text-sm text-slate-500">{t(s.help)}</p>
                <a href={GUIDES[s.key] ?? "/docs"} target="_blank" rel="noopener" className="mt-1 inline-flex items-center gap-1 text-xs text-brand-700 hover:underline"><BookOpen size={12} /> {t("Read the guide")}</a>
              </div>
              {!s.done && s.key !== "notifications" && (s.href ? (
                <Link href={s.href} className="btn-secondary shrink-0 px-3 py-1.5 text-sm">{t("Start")} <ArrowRight size={14} /></Link>
              ) : (
                <button type="button" className="btn-secondary shrink-0 px-3 py-1.5 text-sm" disabled={busy === s.key} onClick={() => act(s.key)}>
                  {busy === s.key && <LoaderCircle className="animate-spin" size={14} />} {t("Resend email")}
                </button>
              ))}
              {!s.done && s.key === "notifications" && (
                <button type="button" className="btn-primary shrink-0 px-3 py-1.5 text-sm" disabled={busy === s.key} onClick={() => act(s.key)}>
                  {busy === s.key && <LoaderCircle className="animate-spin" size={14} />} {t("Turn on")}
                </button>
              )}
            </li>
          ))}
        </ol>

        <button type="button" className="mt-6 text-sm text-slate-500 hover:text-slate-800" onClick={() => Api.dismissOnboarding(!data.dismissed).then(setData)}>
          {data.dismissed ? t("Show the setup reminder in the sidebar again") : t("Hide the setup reminder from the sidebar")}
        </button>
      </div>
    </div>
  );
}
