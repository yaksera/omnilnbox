"use client";

import { useState } from "react";
import clsx from "clsx";
import { Bot, LoaderCircle, Send, UserRound } from "lucide-react";
import { Api } from "@/lib/api";
import type { BotAnswer } from "@/lib/types";
import { useT } from "@/lib/i18n";
import { SourcesLine } from "@/components/inbox/AIAssist";

const TRY = ["kurta ko price kati ho?", "Pokhara ma delivery huncha?", "मलाई २ वटा अर्डर गर्नु छ", "Do you accept eSewa?", "My parcel is late, I want a refund"];

type Turn = { q: string; a?: BotAnswer; error?: string };

export default function PlaygroundTab({ onUsed }: { onUsed: () => void }) {
  const t = useT();
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setBusy(true); setText("");
    const i = turns.length;
    setTurns((prev) => [...prev, { q }]);
    try {
      const a = await Api.aiPlayground(q);
      setTurns((prev) => prev.map((x, j) => (j === i ? { ...x, a } : x)));
      onUsed();
    } catch (err) {
      setTurns((prev) => prev.map((x, j) => (j === i ? { ...x, error: err instanceof Error ? err.message : t("Failed") } : x)));
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <p className="text-sm text-slate-600">{t("Type what a customer might ask and see what the AI would answer from your business info and knowledge base. Each test uses 1 credit. Nothing is sent to anyone.")}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {TRY.map((ex) => <button key={ex} type="button" className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700 hover:bg-slate-200" onClick={() => ask(ex)}>{ex}</button>)}
      </div>
      <div className="card mt-4 min-h-[260px] space-y-4 p-4">
        {turns.length === 0 && <p className="py-16 text-center text-sm text-slate-400">{t("Your test conversation appears here.")}</p>}
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-end gap-2">
              <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-slate-100 px-3 py-2 text-sm">{turn.q}</p>
              <UserRound size={20} className="mt-1 shrink-0 text-slate-400" />
            </div>
            <div className="flex gap-2">
              <Bot size={20} className="mt-1 shrink-0 text-brand-600" />
              {turn.a ? (
                <div className="max-w-[80%]">
                  <p className="rounded-2xl rounded-bl-sm bg-brand-50 px-3 py-2 text-sm text-slate-800">{turn.a.reply}</p>
                  <p className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500">
                    <span className={clsx("rounded-full px-1.5", turn.a.handoff ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-700")}>
                      {turn.a.handoff ? t("Hands over to your team: {reason}", { reason: turn.a.reason || t("needs a human") }) : t("Answered by AI")}
                    </span>
                    <span>{turn.a.category} · {turn.a.sentiment}</span>
                  </p>
                  {turn.a.sources?.length ? <SourcesLine sources={turn.a.sources} className="mt-1" />
                    : !turn.a.handoff && <p className="mt-1 text-[11px] text-amber-700">{t("No knowledge entry was used: add one so the AI answers with your real facts.")}</p>}
                </div>
              ) : turn.error ? <p className="text-sm text-red-700">{turn.error}</p> : <LoaderCircle className="animate-spin text-slate-400" size={18} />}
            </div>
          </div>
        ))}
      </div>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(text); }}>
        <input className="input" placeholder={t("Ask like a customer would…")} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} />
        <button className="btn-primary" disabled={busy || !text.trim()}><Send size={16} /> {t("Test")}</button>
      </form>
    </div>
  );
}
