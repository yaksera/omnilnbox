"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { BookOpen, Bot, BriefcaseBusiness, FlaskConical, LoaderCircle, Workflow } from "lucide-react";
import { Api } from "@/lib/api";
import type { AISettings } from "@/lib/types";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";
import AssistantTab from "@/components/ai/AssistantTab";
import KnowledgeTab from "@/components/ai/KnowledgeTab";
import RulesTab from "@/components/ai/RulesTab";
import PlaygroundTab from "@/components/ai/PlaygroundTab";
import SalesTab from "@/components/ai/SalesTab";

type Tab = "assistant" | "sales" | "knowledge" | "rules" | "test";

export default function AutomationsPage() {
  const t = useT();
  const { can } = useMe();
  const canEdit = can("manage_automations");
  const [tab, setTab] = useState<Tab>("assistant");
  const [cfg, setCfg] = useState<AISettings | null>(null);
  const [error, setError] = useState("");

  const reload = () => Api.aiSettings().then(setCfg).catch((e) => setError(e instanceof Error ? e.message : t("Couldn't load")));
  useEffect(() => {
    reload();
    const h = window.location.hash.slice(1);
    if (["assistant", "sales", "knowledge", "rules", "test"].includes(h)) setTab(h as Tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on open
  }, []);

  function go(next: Tab) {
    setTab(next);
    window.history.replaceState(null, "", `#${next}`);
  }

  if (error) return <div className="p-6"><p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p></div>;
  if (!cfg) return <div className="flex h-full items-center justify-center"><LoaderCircle className="animate-spin text-slate-400" /></div>;

  const TABS: Array<[Tab, string, typeof Bot, string?]> = [
    ["assistant", "AI assistant", Bot, cfg.bot_mode !== "off" ? "on" : undefined],
    ["sales", "Sales staff", BriefcaseBusiness, cfg.bot_mode !== "off" && (cfg.sales_orders || cfg.sales_bookings) ? "on" : undefined],
    ["knowledge", "Knowledge base", BookOpen, String(cfg.knowledge_count)],
    ["rules", "Automations", Workflow],
    ["test", "Test the AI", FlaskConical],
  ];

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <h1 className="text-xl font-bold">{t("AI & Automations")}</h1>
      <p className="text-sm text-slate-500">{t("Answer customers 24/7, reply to comments in DMs, and let AI draft replies for your team.")}</p>
      <div className="mt-5 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map(([key, label, Icon, badge]) => (
          <button key={key} type="button" onClick={() => go(key)}
            className={clsx("-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
              tab === key ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800")}>
            <Icon size={16} /> {t(label)}
            {badge && <span className={clsx("rounded-full px-1.5 text-[10px]", badge === "on" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600")}>{badge === "on" ? t("on") : badge}</span>}
          </button>
        ))}
      </div>
      <div className="mt-5">
        {tab === "assistant" && <AssistantTab cfg={cfg} canEdit={canEdit} onSaved={setCfg} />}
        {tab === "sales" && <SalesTab cfg={cfg} canEdit={canEdit} onSaved={setCfg} goAssistant={() => go("assistant")} />}
        {tab === "knowledge" && <KnowledgeTab canEdit={canEdit} onCount={(n) => setCfg((c) => (c ? { ...c, knowledge_count: n } : c))} />}
        {tab === "rules" && <RulesTab canEdit={canEdit} enabled={cfg.features.automations} aiEnabled={cfg.features.ai} />}
        {tab === "test" && <PlaygroundTab onUsed={reload} />}
      </div>
    </div>
  );
}
