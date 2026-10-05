"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { Check, ChevronDown, LoaderCircle, Receipt, ShieldAlert, ShieldCheck, ShieldQuestion, X } from "lucide-react";
import { Api } from "@/lib/api";
import type { PaymentCheck } from "@/lib/types";
import { money } from "@/components/commerce/ui";
import { useT } from "@/lib/i18n";

const STYLE = {
  valid: { icon: ShieldCheck, cls: "border-emerald-200 bg-emerald-50", text: "text-emerald-800" },
  check: { icon: ShieldQuestion, cls: "border-amber-200 bg-amber-50", text: "text-amber-900" },
  suspicious: { icon: ShieldAlert, cls: "border-red-200 bg-red-50", text: "text-red-800" },
  not_payment: { icon: Receipt, cls: "border-slate-200 bg-slate-50", text: "text-slate-700" },
} as const;

/** Payment screenshots in this conversation that wait for a staff decision. Shown above the reply box. */
export default function PaymentChecks({ conversationId, refreshKey, onChanged }: { conversationId: string; refreshKey: number; onChanged?: () => void }) {
  const t = useT();
  const [checks, setChecks] = useState<PaymentCheck[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Api.paymentChecks({ conversation: conversationId, status: "pending" }).then(setChecks).catch(() => setChecks([]));
  }, [conversationId, refreshKey]);

  if (!checks.length) return null;

  async function act(c: PaymentCheck, action: "confirm" | "reject") {
    setBusy(c.id); setError("");
    try {
      if (action === "confirm") await Api.confirmPaymentCheck(c.id);
      else {
        const msg = window.prompt(t("Message to the customer (optional):"), t("Sorry, we couldn't verify this payment. Could you please send the transaction ID or a clearer screenshot?"));
        if (msg === null) return;
        await Api.rejectPaymentCheck(c.id, msg);
      }
      setChecks((cs) => cs.filter((x) => x.id !== c.id));
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Failed"));
    } finally { setBusy(null); }
  }

  return (
    <div className="space-y-2 border-t border-slate-200 bg-white px-3 pt-3">
      {checks.map((c) => {
        const s = STYLE[c.verdict];
        const Icon = s.icon;
        const expanded = open === c.id || c.verdict === "suspicious";
        return (
          <div key={c.id} className={clsx("rounded-xl border p-2.5 text-sm", s.cls)}>
            <div className="flex items-center gap-2">
              <Icon size={18} className={clsx("shrink-0", s.text)} />
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setOpen(open === c.id ? null : c.id)}>
                <span className={clsx("block font-semibold", s.text)}>{t(c.verdict_label)}: {c.amount ? money(c.amount) : t("amount unreadable")} · {c.app_label}</span>
                <span className="block truncate text-xs text-slate-600">
                  {c.order ? t("For order {number}", { number: c.order.number }) : t("No matching order")}{c.txn_id && ` · ${c.txn_id}`}
                </span>
              </button>
              <ChevronDown size={16} className={clsx("shrink-0 text-slate-400 transition", expanded && "rotate-180")} />
            </div>
            {expanded && (
              <ul className="mt-2 space-y-0.5 pl-7 text-xs text-slate-700">
                {c.reasons.map((r) => <li key={r} className={clsx(r.startsWith("⚠") && "font-medium text-red-700")}>{r}</li>)}
              </ul>
            )}
            <div className="mt-2 flex gap-2 pl-7">
              <button type="button" disabled={busy === c.id || !c.order} onClick={() => act(c, "confirm")}
                className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                title={c.order ? "" : t("No unpaid order to mark as paid. Create the order first.")}>
                {busy === c.id ? <LoaderCircle size={14} className="animate-spin" /> : <Check size={14} />} {c.order ? t("Confirm paid") : t("No order")}
              </button>
              <button type="button" disabled={busy === c.id} onClick={() => act(c, "reject")}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">
                <X size={14} /> {t("Reject")}
              </button>
            </div>
          </div>
        );
      })}
      {error && <p className="text-xs text-red-700">{error}</p>}
    </div>
  );
}
