"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import Link from "next/link";
import { BookOpen, Bot, ChevronDown, LoaderCircle, Pause, Play, Sparkles, Wand2, X } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import type { AISummary, Conversation, KnowledgeRef, RewriteMode } from "@/lib/types";
import { useT } from "@/lib/i18n";

type T = ReturnType<typeof useT>;

function aiError(err: unknown, t: T) {
  if (err instanceof ApiError && err.status === 402) return err.message || t("Not included in your plan.");
  return err instanceof Error ? err.message : t("AI request failed");
}

/** "Based on: Fee structure (Prospectus.pdf)": which knowledge an AI answer used. Staff only; click to check or fix it. */
export function SourcesLine({ sources, className, tone = "light" }: { sources?: KnowledgeRef[]; className?: string; tone?: "light" | "plain" }) {
  const t = useT();
  if (!sources?.length) return null;
  return (
    <p className={clsx("flex flex-wrap items-center gap-1 text-[11px]", tone === "light" ? "text-violet-700" : "text-slate-500", className)}>
      <BookOpen size={11} className="shrink-0" /> {t("Based on:")}
      {sources.map((s) => {
        const label = s.source && s.kind === "knowledge" ? `${s.title} · ${s.source}` : s.title;
        return s.kind === "knowledge" ? (
          <Link key={`${s.kind}-${s.id}`} href={`/automations?k=${s.id}#knowledge`} title={t("Open this entry to check or correct it")}
            className="max-w-[260px] truncate rounded bg-violet-50 px-1.5 py-0.5 font-medium hover:bg-violet-100 hover:underline">{label}</Link>
        ) : <span key={`${s.kind}-${s.id}`} className="max-w-[260px] truncate rounded bg-slate-100 px-1.5 py-0.5">{label}</span>;
      })}
    </p>
  );
}

/** ✨ Suggest reply: drafts an answer from the knowledge base into the composer. */
export function SuggestButton({ conversationId, onDraft, onError }: {
  conversationId: string; onDraft: (text: string, missing: string, sources?: KnowledgeRef[]) => void; onError: (msg: string) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  return (
    <button type="button" disabled={busy} title={t("Draft a reply with AI from your knowledge base")}
      onClick={async () => {
        setBusy(true); onError("");
        try {
          const r = await Api.aiSuggest(conversationId);
          onDraft(r.reply, r.missing, r.sources);
        } catch (err) { onError(aiError(err, t)); } finally { setBusy(false); }
      }}
      className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-60">
      {busy ? <LoaderCircle size={13} className="animate-spin" /> : <Sparkles size={13} />} {t("Suggest reply")}
    </button>
  );
}

const MODES: Array<[RewriteMode, string]> = [
  ["improve", "Fix grammar & polish"], ["friendlier", "Friendlier"], ["professional", "More professional"], ["shorter", "Shorter"],
  ["nepali", "Translate to नेपाली"], ["romanized", "Translate to Romanized Nepali"], ["english", "Translate to English"],
];

export function RewriteMenu({ text, onText, onError }: { text: string; onText: (t: string) => void; onError: (msg: string) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button type="button" disabled={!text.trim() || busy} onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40">
        {busy ? <LoaderCircle size={13} className="animate-spin" /> : <Wand2 size={13} />} {t("Rewrite")} <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute bottom-8 left-0 z-30 w-56 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          {MODES.map(([m, label]) => (
            <button key={m} type="button" className="block w-full rounded px-2.5 py-1.5 text-left text-sm hover:bg-slate-50"
              onClick={async () => {
                setOpen(false); setBusy(true); onError("");
                try { onText((await Api.aiRewrite(text, m)).text); } catch (err) { onError(aiError(err, t)); } finally { setBusy(false); }
              }}>{t(label)}</button>
          ))}
        </div>
      )}
    </div>
  );
}

const SENTIMENT_LABELS: Record<string, string> = { positive: "Positive", neutral: "Neutral", negative: "Negative" };
const CATEGORY_LABELS: Record<string, string> = {
  order: "Order", question: "Question", lead: "Lead", complaint: "Complaint", support: "Support", feedback: "Feedback", spam: "Spam", other: "Other",
};

const SENTIMENT = { positive: "bg-emerald-50 text-emerald-700", neutral: "bg-slate-100 text-slate-600", negative: "bg-red-50 text-red-700" };

/** AI assistant on/off for this conversation + the AI's label. */
export function BotChip({ conversation, onChanged }: { conversation: Conversation; onChanged: (c: Conversation) => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const ai = conversation.ai;
  if (!ai) return null;
  const reason = ai.pause_reason === "agent" ? t("an agent replied")
    : ai.pause_reason === "handoff" ? (ai.handoff_reason ? t("handed to team: {reason}", { reason: ai.handoff_reason }) : t("handed to team"))
    : t("paused manually");
  return (
    <span className="inline-flex items-center gap-1">
      <button type="button" disabled={busy}
        title={ai.bot_paused ? t("AI assistant is paused here ({reason}). Click to let it answer again.", { reason }) : t("AI assistant may answer this customer. Click to pause it here.")}
        onClick={async () => {
          setBusy(true);
          try { onChanged(await Api.setBotPaused(conversation.id, !ai.bot_paused)); } finally { setBusy(false); }
        }}
        className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
          ai.bot_paused ? "bg-slate-100 text-slate-600 hover:bg-slate-200" : "bg-brand-50 text-brand-700 hover:bg-brand-100")}>
        <Bot size={11} /> {ai.bot_paused ? t("AI paused") : t("AI on")} {ai.bot_paused ? <Play size={10} /> : <Pause size={10} />}
      </button>
      {ai.sentiment === "negative" && <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-medium", SENTIMENT.negative)}>{t("Unhappy customer")}</span>}
    </span>
  );
}

export function SummaryCard({ conversation, onChanged }: { conversation: Conversation; onChanged: (c: Conversation) => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(false);
  const s: AISummary | null | undefined = conversation.ai?.summary;

  async function run() {
    setBusy(true); setError(""); setHidden(false);
    try {
      const summary = await Api.aiSummary(conversation.id);
      onChanged({ ...conversation, ai: { ...conversation.ai!, summary, category: summary.category, sentiment: summary.sentiment } });
    } catch (err) { setError(aiError(err, t)); } finally { setBusy(false); }
  }

  if (!s || hidden) {
    return (
      <span className="inline-flex items-center gap-2">
        <button type="button" onClick={run} disabled={busy}
          className="inline-flex items-center gap-1 rounded-full border border-brand-200 px-2 py-0.5 text-[11px] font-medium text-brand-700 hover:bg-brand-50">
          {busy ? <LoaderCircle size={11} className="animate-spin" /> : <Sparkles size={11} />} {t("Summarize")}
        </button>
        {error && <span className="text-[11px] text-red-600">{error}</span>}
      </span>
    );
  }
  return (
    <div className="mt-1 w-full rounded-lg border border-brand-100 bg-brand-50/50 p-2.5 text-xs text-slate-700">
      <div className="flex items-start gap-2">
        <Sparkles size={14} className="mt-0.5 shrink-0 text-brand-600" />
        <div className="min-w-0 flex-1">
          <p>{s.summary}</p>
          {s.next_step && <p className="mt-1"><b>{t("Next:")}</b> {s.next_step}</p>}
          <p className="mt-1 flex flex-wrap gap-1">
            <span className="rounded-full bg-white px-1.5 capitalize ring-1 ring-slate-200">{CATEGORY_LABELS[s.category] ? t(CATEGORY_LABELS[s.category]) : s.category}</span>
            <span className={clsx("rounded-full px-1.5 capitalize", SENTIMENT[s.sentiment])}>{SENTIMENT_LABELS[s.sentiment] ? t(SENTIMENT_LABELS[s.sentiment]) : s.sentiment}</span>
            <button type="button" className="text-brand-700 hover:underline" onClick={run} disabled={busy}>{busy ? t("Updating…") : t("Refresh")}</button>
          </p>
        </div>
        <button type="button" aria-label={t("Hide summary")} onClick={() => setHidden(true)} className="text-slate-400 hover:text-slate-600"><X size={14} /></button>
      </div>
    </div>
  );
}
