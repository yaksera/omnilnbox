"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import {
  BadgeCheck, Ban, Check, Clock, Copy, Gift, Link2, LoaderCircle, MousePointerClick, Pencil, Send, Users, Wallet,
} from "lucide-react";
import { Api } from "@/lib/api";
import type {
  AffiliateDashboard, CommissionState, Money, PayoutDetails, PayoutMethod, ReferredWorkspaceStatus,
} from "@/lib/types";
import { money } from "@/lib/money";
import { useT } from "@/lib/i18n";

const METHODS: Array<{ key: PayoutMethod; label: string; numberLabel: string }> = [
  { key: "esewa", label: "eSewa", numberLabel: "eSewa ID (mobile number)" },
  { key: "khalti", label: "Khalti", numberLabel: "Khalti ID (mobile number)" },
  { key: "bank", label: "Bank transfer", numberLabel: "Account number" },
];

const STATE_STYLE: Record<CommissionState, string> = {
  holding: "bg-amber-50 text-amber-800", available: "bg-emerald-50 text-emerald-700", requested: "bg-sky-50 text-sky-700",
  paid: "bg-slate-100 text-slate-600", void: "bg-red-50 text-red-700",
};
const STATE_LABEL: Record<CommissionState, string> = {
  holding: "Holding", available: "Available", requested: "Payout requested", paid: "Paid", void: "Void",
};
const REF_STATUS: Record<ReferredWorkspaceStatus, [string, string]> = {
  subscribed: ["Subscribed", "bg-emerald-50 text-emerald-700"], trial: ["On trial", "bg-sky-50 text-sky-700"],
  cancelled: ["Cancelled", "bg-slate-100 text-slate-600"], free: ["Free plan", "bg-slate-100 text-slate-600"],
};

const pct = (rate: string) => `${Math.round(Number(rate) * 100)}%`;
const date = (v: string | null) => (v ? new Date(v).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");

/** "Rs. 1,600" or "Rs. 1,600 + $5.80" (USD only when there is some). */
function both(m: Money) {
  const usd = Number(m.USD);
  return usd ? `${money(m.NPR, "NPR")} + ${money(m.USD, "USD")}` : money(m.NPR, "NPR");
}

function CopyField({ label, value }: { label: string; value: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">{t(label)}</p>
      <div className="mt-1 flex gap-2">
        <input readOnly value={value} className="input flex-1 bg-slate-50 font-mono text-sm" onFocus={(e) => e.target.select()} />
        <button type="button" className="btn-secondary shrink-0" onClick={async () => {
          try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* blocked */ }
        }}>
          {copied ? <Check size={16} className="text-emerald-600" /> : <Copy size={16} />} {copied ? t("Copied") : t("Copy")}
        </button>
      </div>
    </div>
  );
}

function Tile({ icon: Icon, label, value, sub }: { icon: typeof Users; label: string; value: string | number; sub?: string }) {
  const t = useT();
  return (
    <div className="card p-4">
      <p className="flex items-center gap-1.5 text-xs font-medium text-slate-500"><Icon size={14} /> {t(label)}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

function PayoutForm({ initial, onSubmit, submitLabel, withCode, suggestedCode, busy }: {
  initial?: { method?: PayoutMethod | ""; details?: Partial<PayoutDetails> }; onSubmit: (v: {
    code: string; payout_method: PayoutMethod; payout_details: PayoutDetails; pitch: string;
  }) => void; submitLabel: string; withCode?: boolean; suggestedCode?: string; busy: boolean;
}) {
  const t = useT();
  const [code, setCode] = useState(suggestedCode ?? "");
  const [method, setMethod] = useState<PayoutMethod>((initial?.method || "esewa") as PayoutMethod);
  const [details, setDetails] = useState<PayoutDetails>({
    account_name: initial?.details?.account_name ?? "", account_number: initial?.details?.account_number ?? "",
    bank_name: initial?.details?.bank_name ?? "",
  });
  const [pitch, setPitch] = useState("");
  const m = METHODS.find((x) => x.key === method)!;
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); onSubmit({ code, payout_method: method, payout_details: details, pitch }); }}>
      {withCode && (
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">{t("Your promo code")}</span>
          <input className="input font-mono uppercase" value={code} maxLength={20} required minLength={4}
            onChange={(e) => setCode(e.target.value.replace(/[^A-Za-z0-9]/g, "").toUpperCase())} />
          <span className="mt-1 block text-xs text-slate-500">{t("4-20 letters or numbers. It's also your link: {link}", { link: `/r/${code || "CODE"}` })}</span>
        </label>
      )}
      <div className="text-sm">
        <span className="mb-1 block font-medium text-slate-700">{t("How should we pay you?")}</span>
        <div className="flex flex-wrap gap-2">
          {METHODS.map((x) => (
            <button key={x.key} type="button" onClick={() => setMethod(x.key)}
              className={clsx("rounded-lg border px-3 py-1.5 text-sm font-medium", method === x.key ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600 hover:bg-slate-50")}>
              {t(x.label)}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">{t("Account holder name")}</span>
          <input className="input" required maxLength={120} value={details.account_name} onChange={(e) => setDetails({ ...details, account_name: e.target.value })} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">{t(m.numberLabel)}</span>
          <input className="input" required maxLength={60} value={details.account_number} onChange={(e) => setDetails({ ...details, account_number: e.target.value })} />
        </label>
        {method === "bank" && (
          <label className="block text-sm sm:col-span-2">
            <span className="mb-1 block font-medium text-slate-700">{t("Bank and branch")}</span>
            <input className="input" required maxLength={120} value={details.bank_name ?? ""} placeholder="Nabil Bank, Durbarmarg"
              onChange={(e) => setDetails({ ...details, bank_name: e.target.value })} />
          </label>
        )}
      </div>
      {withCode && (
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">{t("How will you promote OmniInbox? (optional)")}</span>
          <textarea className="input min-h-[80px]" maxLength={2000} value={pitch} onChange={(e) => setPitch(e.target.value)}
            placeholder={t("e.g. my YouTube channel for online sellers, a Facebook group, my clients…")} />
        </label>
      )}
      <button className="btn-primary" disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={16} />} {t(submitLabel)}</button>
    </form>
  );
}

export default function AffiliatePage() {
  const t = useT();
  const [data, setData] = useState<AffiliateDashboard | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => { Api.affiliateMe().then(setData).catch((e) => setError(e.message)); }, []);
  useEffect(() => { load(); }, [load]);

  async function run(key: string, fn: () => Promise<unknown>, ok?: string) {
    setBusy(key); setError(""); setNotice("");
    try { await fn(); if (ok) setNotice(t(ok)); load(); } catch (e) { setError(e instanceof Error ? e.message : t("Something went wrong")); }
    finally { setBusy(""); }
  }

  if (!data) {
    return <div className="flex h-full items-center justify-center text-slate-400">{error ? <p className="text-sm text-red-600">{error}</p> : <LoaderCircle className="animate-spin" />}</div>;
  }
  const { program, affiliate: a } = data;
  const rate = pct(a?.rate ?? program.rate);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold"><Gift size={22} className="text-brand-600" /> {t("Affiliate program")}</h1>
          <p className="mt-1 text-sm text-slate-600">
            {t("Earn {rate} of every payment from businesses you refer, every month, for as long as they stay subscribed.", { rate })}
          </p>
        </div>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{t(error)}</p>}
        {notice && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</p>}

        {!a && (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              {[
                [Link2, "Share your link or code", "Post it on Facebook, TikTok, YouTube or send it to businesses you know."],
                [Users, "They subscribe", "They sign up through your link, or enter your promo code on the sign-up or Billing page."],
                [Wallet, "You earn every month", "Get {rate} of each payment they make, as long as they stay subscribed. Paid to eSewa, Khalti or your bank."],
              ].map(([Icon, title, body], i) => {
                const I = Icon as typeof Users;
                return (
                  <div key={i} className="card p-4">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><I size={18} /></span>
                    <p className="mt-3 font-semibold">{t(title as string)}</p>
                    <p className="mt-1 text-sm text-slate-600">{t(body as string, { rate })}</p>
                  </div>
                );
              })}
            </div>
            <div className="card p-5">
              <h2 className="text-lg font-semibold">{t("Apply to become an affiliate")}</h2>
              <p className="mb-4 mt-1 text-sm text-slate-600">
                {t("We review applications within 1-2 days. Commissions become payable {days} days after each payment, and you can withdraw once you have {min}.",
                  { days: program.hold_days, min: money(program.min_payout.NPR, "NPR") })}
              </p>
              <PayoutForm withCode suggestedCode={data.suggested_code} submitLabel="Apply now" busy={busy === "apply"}
                onSubmit={(v) => run("apply", () => Api.affiliateApply(v), "Application sent. We'll email you once it's approved.")} />
            </div>
          </>
        )}

        {a && a.status === "pending" && (
          <div className="card flex items-start gap-3 p-5">
            <Clock className="mt-0.5 shrink-0 text-amber-600" size={20} />
            <div>
              <p className="font-semibold">{t("Your application is being reviewed")}</p>
              <p className="mt-1 text-sm text-slate-600">{t("Your code {code} will start working once we approve it. We'll email you.", { code: a.code })}</p>
            </div>
          </div>
        )}

        {a && (a.status === "rejected" || a.status === "suspended") && (
          <div className="card flex items-start gap-3 p-5">
            <Ban className="mt-0.5 shrink-0 text-red-600" size={20} />
            <div>
              <p className="font-semibold">{a.status === "rejected" ? t("Your application wasn't approved") : t("Your affiliate account is suspended")}</p>
              {a.admin_note && <p className="mt-1 text-sm text-slate-600">{t("Reason: {reason}", { reason: a.admin_note })}</p>}
              <p className="mt-1 text-sm text-slate-600">{t("Questions? Contact OmniInbox support.")}</p>
            </div>
          </div>
        )}

        {a && a.status === "approved" && data.stats && data.balances && (
          <>
            <div className="card space-y-4 p-5">
              <p className="flex items-center gap-2 text-sm font-semibold text-emerald-700"><BadgeCheck size={16} /> {t("You're an approved affiliate · {rate} recurring", { rate })}</p>
              <div className="grid gap-4 md:grid-cols-2">
                <CopyField label="Your tracking link" value={a.link} />
                <CopyField label="Your promo code" value={a.code} />
              </div>
              <p className="text-xs text-slate-500">{t("Anyone who opens your link is remembered for 60 days. They can also type your code when signing up or on the Billing page before their first payment.")}</p>
            </div>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Tile icon={MousePointerClick} label="Link clicks" value={data.stats.clicks} sub={t("{n} in the last 30 days", { n: data.stats.clicks_30d })} />
              <Tile icon={Users} label="Sign-ups" value={data.stats.signups} />
              <Tile icon={BadgeCheck} label="Paying customers" value={data.stats.paying} />
              <Tile icon={Wallet} label="Total earned" value={both(data.balances.lifetime)} />
            </div>

            <div className="card p-5">
              <h2 className="text-lg font-semibold">{t("Balance")}</h2>
              <div className="mt-3 grid gap-4 sm:grid-cols-4">
                {([
                  ["available", "Available to withdraw", "text-emerald-700"],
                  ["holding", "Holding", "text-amber-700"],
                  ["requested", "Payout requested", "text-sky-700"],
                  ["paid", "Paid to you", "text-slate-700"],
                ] as const).map(([k, label, color]) => (
                  <div key={k}>
                    <p className="text-xs font-medium text-slate-500">{t(label)}</p>
                    <p className={clsx("mt-1 text-xl font-semibold tabular-nums", color)}>{both(data.balances![k])}</p>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-slate-500">{t("New commissions are held for {days} days in case of refunds, then become available.", { days: program.hold_days })}</p>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
                {(["NPR", "USD"] as const).filter((c) => c === "NPR" || Number(data.balances!.lifetime.USD) > 0).map((c) => {
                  const avail = Number(data.balances!.available[c]);
                  const min = Number(program.min_payout[c]);
                  return (
                    <button key={c} className="btn-primary" disabled={!!busy || avail < min || avail <= 0}
                      onClick={() => run(`payout-${c}`, () => Api.affiliatePayout(c), "Payout requested. We'll send it within a few working days.")}>
                      {busy === `payout-${c}` ? <LoaderCircle className="animate-spin" size={16} /> : <Send size={16} />}
                      {t("Withdraw {amount}", { amount: money(avail, c) })}
                    </button>
                  );
                })}
                <span className="text-xs text-slate-500">{t("Minimum withdrawal: {min}", { min: money(program.min_payout.NPR, "NPR") })}</span>
              </div>
            </div>
          </>
        )}

        {a && a.status !== "rejected" && (
          <div className="card p-5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">{t("Payout details")}</h2>
              {!editing && <button className="btn-ghost text-sm" onClick={() => setEditing(true)}><Pencil size={14} /> {t("Edit")}</button>}
            </div>
            {editing ? (
              <div className="mt-3">
                <PayoutForm initial={{ method: a.payout_method, details: a.payout_details as Partial<PayoutDetails> }} submitLabel="Save"
                  busy={busy === "details"}
                  onSubmit={(v) => run("details", async () => {
                    await Api.affiliateUpdate({ payout_method: v.payout_method, payout_details: v.payout_details });
                    setEditing(false);
                  }, "Payout details saved.")} />
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-700">
                {METHODS.find((m) => m.key === a.payout_method)?.label ?? "—"} · {(a.payout_details as PayoutDetails)?.account_name} · {(a.payout_details as PayoutDetails)?.account_number}
                {(a.payout_details as PayoutDetails)?.bank_name ? ` · ${(a.payout_details as PayoutDetails).bank_name}` : ""}
              </p>
            )}
          </div>
        )}

        {a && a.status === "approved" && (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card overflow-hidden">
              <h2 className="border-b border-slate-100 px-5 py-3 font-semibold">{t("Commissions")}</h2>
              {!data.commissions?.length ? <p className="p-5 text-sm text-slate-500">{t("No commissions yet. They appear here when someone you referred pays.")}</p> : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {data.commissions.map((c) => (
                    <li key={c.id} className="flex items-center gap-3 px-5 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-slate-800">{c.workspace} <span className="font-normal text-slate-500">· {c.plan} {t(c.cycle === "yearly" ? "yearly" : "monthly")}</span></p>
                        <p className="text-xs text-slate-500">
                          {t("{rate} of {amount} · {date}", { rate: pct(c.rate), amount: money(c.base_amount, c.currency), date: date(c.created_at) })}
                          {c.state === "holding" && ` · ${t("available {date}", { date: date(c.available_at) })}`}
                        </p>
                      </div>
                      <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", STATE_STYLE[c.state])}>{t(STATE_LABEL[c.state])}</span>
                      <span className="w-24 text-right font-semibold tabular-nums">{money(c.amount, c.currency)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-6">
              <div className="card overflow-hidden">
                <h2 className="border-b border-slate-100 px-5 py-3 font-semibold">{t("Businesses you referred")}</h2>
                {!data.referrals?.length ? <p className="p-5 text-sm text-slate-500">{t("No sign-ups yet. Share your link to get started.")}</p> : (
                  <ul className="divide-y divide-slate-100 text-sm">
                    {data.referrals.map((r, i) => (
                      <li key={i} className="flex items-center gap-3 px-5 py-2.5">
                        <span className="flex-1 font-medium text-slate-800">{r.workspace}</span>
                        <span className="text-xs text-slate-500">{r.source === "link" ? t("via link") : t("via code")} · {date(r.joined_at)}</span>
                        <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", REF_STATUS[r.status][1])}>{t(REF_STATUS[r.status][0])}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {!!data.payouts?.length && (
                <div className="card overflow-hidden">
                  <h2 className="border-b border-slate-100 px-5 py-3 font-semibold">{t("Payouts")}</h2>
                  <ul className="divide-y divide-slate-100 text-sm">
                    {data.payouts.map((p) => (
                      <li key={p.id} className="flex items-center gap-3 px-5 py-2.5">
                        <div className="min-w-0 flex-1">
                          <p className="font-medium">{money(p.amount, p.currency)}</p>
                          <p className="text-xs text-slate-500">
                            {t("Requested {date}", { date: date(p.requested_at) })}
                            {p.reference && ` · ${t("Txn {ref}", { ref: p.reference })}`}
                            {p.status === "rejected" && p.note && ` · ${p.note}`}
                          </p>
                        </div>
                        <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium",
                          p.status === "paid" ? "bg-emerald-50 text-emerald-700" : p.status === "rejected" ? "bg-red-50 text-red-700" : "bg-sky-50 text-sky-700")}>
                          {t(p.status === "paid" ? "Paid" : p.status === "rejected" ? "Rejected" : "Processing")}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
