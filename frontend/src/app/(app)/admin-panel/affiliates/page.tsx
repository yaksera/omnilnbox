"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { ArrowLeft, Ban, Check, Gift, LoaderCircle, RotateCcw, Search, Send, X } from "lucide-react";
import { Api } from "@/lib/api";
import type { AdminAffiliateDetail, AdminAffiliateList, AffiliatePayout, AffiliateStatus, Money } from "@/lib/types";
import { useMe } from "@/components/AppShell";
import { money } from "@/lib/money";
import { useT } from "@/lib/i18n";

const STATUS_STYLE: Record<AffiliateStatus, string> = {
  pending: "bg-amber-50 text-amber-800", approved: "bg-emerald-50 text-emerald-700",
  rejected: "bg-slate-100 text-slate-600", suspended: "bg-red-50 text-red-700",
};
const STATUS_LABEL: Record<AffiliateStatus, string> = { pending: "Pending review", approved: "Approved", rejected: "Rejected", suspended: "Suspended" };
const FILTERS = [["", "All"], ["pending", "Pending review"], ["approved", "Approved"], ["suspended", "Suspended"], ["rejected", "Rejected"]] as const;
const METHOD_LABEL: Record<string, string> = { esewa: "eSewa", khalti: "Khalti", bank: "Bank" };

const pct = (rate: string) => `${Math.round(Number(rate) * 100)}%`;
const date = (v: string | null) => (v ? new Date(v).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");
function both(m: Money) {
  return Number(m.USD) ? `${money(m.NPR, "NPR")} + ${money(m.USD, "USD")}` : money(m.NPR, "NPR");
}

function Tile({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: "warn" }) {
  const t = useT();
  return (
    <div className="card p-4">
      <p className="text-xs font-medium text-slate-500">{t(label)}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      {sub && <p className={clsx("mt-0.5 text-xs", tone === "warn" ? "text-amber-700" : "text-slate-500")}>{sub}</p>}
    </div>
  );
}

function PayoutRow({ p, onDone }: { p: AffiliatePayout; onDone: () => void }) {
  const t = useT();
  const [ref, setRef] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function act(action: "paid" | "reject") {
    setBusy(true); setError("");
    try { await Api.platformPayoutAction(p.id, { action, reference: ref, note }); onDone(); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  }
  return (
    <li className="space-y-2 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-lg font-semibold tabular-nums">{money(p.amount, p.currency)}</span>
        <span className="text-slate-600">{p.affiliate?.name} ({p.affiliate?.code}) · {t("requested {date}", { date: date(p.requested_at) })}</span>
      </div>
      <p className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
        {METHOD_LABEL[p.method] ?? p.method} · {p.details?.account_name} · {p.details?.account_number}{p.details?.bank_name ? ` · ${p.details.bank_name}` : ""}
      </p>
      <div className="flex flex-wrap gap-2">
        <input className="input w-48 py-1.5 text-sm" placeholder={t("Transaction ID")} value={ref} onChange={(e) => setRef(e.target.value)} />
        <input className="input min-w-0 flex-1 py-1.5 text-sm" placeholder={t("Note (optional; required to reject)")} value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="btn-primary py-1.5" disabled={busy || !ref.trim()} onClick={() => act("paid")}><Check size={15} /> {t("Mark paid")}</button>
        <button className="btn-secondary py-1.5 text-red-600" disabled={busy || !note.trim()} onClick={() => act("reject")}><X size={15} /> {t("Reject")}</button>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </li>
  );
}

function Drawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const t = useT();
  const [d, setD] = useState<AdminAffiliateDetail | null>(null);
  const [note, setNote] = useState("");
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { Api.platformAffiliate(id).then((x) => { setD(x); setRate(String(Math.round(Number(x.rate) * 100))); }).catch((e) => setError(e.message)); }, [id]);
  async function act(action: "approve" | "reject" | "suspend" | "reactivate" | "set_rate") {
    setBusy(true); setError("");
    try {
      const x = await Api.platformAffiliateAction(id, { action, note, ...(action === "set_rate" || action === "approve" ? { rate: Number(rate) } : {}) });
      setD(x); setNote(""); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  }
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div className="scroll-thin h-full w-full max-w-xl overflow-y-auto bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 flex items-center justify-between border-b border-slate-100 bg-white px-5 py-4">
          <h3 className="font-semibold">{d ? `${d.name} · ${d.code}` : t("Affiliate")}</h3>
          <button onClick={onClose} aria-label={t("Close")} className="text-slate-400 hover:text-slate-700"><X size={20} /></button>
        </div>
        {!d ? <div className="flex justify-center p-10 text-slate-400"><LoaderCircle className="animate-spin" /></div> : (
          <div className="space-y-5 p-5 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_STYLE[d.status])}>{t(STATUS_LABEL[d.status])}</span>
              <span className="text-slate-600">{d.email} · {t("applied {date}", { date: date(d.created_at) })}</span>
            </div>
            {d.pitch && <p className="rounded-lg bg-slate-50 px-3 py-2 text-slate-700"><b>{t("How they'll promote:")}</b> {d.pitch}</p>}
            <p className="text-slate-700"><b>{t("Payout to:")}</b> {METHOD_LABEL[d.payout_method ?? ""] ?? "—"} · {d.payout_details?.account_name} · {d.payout_details?.account_number}</p>
            <div className="grid grid-cols-3 gap-3">
              <div><p className="text-xs text-slate-500">{t("Clicks")}</p><p className="text-lg font-semibold">{d.stats.clicks}</p></div>
              <div><p className="text-xs text-slate-500">{t("Sign-ups")}</p><p className="text-lg font-semibold">{d.stats.signups}</p></div>
              <div><p className="text-xs text-slate-500">{t("Paying")}</p><p className="text-lg font-semibold">{d.stats.paying}</p></div>
              <div className="col-span-3"><p className="text-xs text-slate-500">{t("Earned all time")}</p><p className="text-lg font-semibold">{both(d.balances.lifetime)}</p></div>
            </div>

            <div className="space-y-2 rounded-xl border border-slate-200 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-slate-600">{t("Commission rate")}</label>
                <input className="input w-20 py-1.5 text-sm" type="number" min={0} max={90} value={rate} onChange={(e) => setRate(e.target.value)} />
                <span className="text-slate-500">%</span>
                {d.status !== "pending" && <button className="btn-secondary py-1.5" disabled={busy} onClick={() => act("set_rate")}>{t("Save rate")}</button>}
              </div>
              <input className="input py-1.5 text-sm" placeholder={t("Note to the affiliate (needed to reject or suspend)")} value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                {d.status === "pending" && <button className="btn-primary py-1.5" disabled={busy} onClick={() => act("approve")}><Check size={15} /> {t("Approve")}</button>}
                {d.status === "pending" && <button className="btn-secondary py-1.5" disabled={busy || !note.trim()} onClick={() => act("reject")}><X size={15} /> {t("Reject")}</button>}
                {d.status === "approved" && <button className="btn-secondary py-1.5 text-red-600" disabled={busy || !note.trim()} onClick={() => act("suspend")}><Ban size={15} /> {t("Suspend")}</button>}
                {(d.status === "suspended" || d.status === "rejected") && <button className="btn-primary py-1.5" disabled={busy} onClick={() => act("reactivate")}><RotateCcw size={15} /> {t("Reactivate")}</button>}
              </div>
              {error && <p className="text-xs text-red-600">{error}</p>}
            </div>

            <div>
              <p className="mb-2 font-semibold">{t("Referred workspaces")}</p>
              {!d.referrals.length ? <p className="text-slate-500">{t("None yet.")}</p> : (
                <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {d.referrals.map((r) => (
                    <li key={r.workspace.id} className="flex items-center gap-2 px-3 py-2">
                      <span className="flex-1 font-medium">{r.workspace.name}</span>
                      <span className="text-xs text-slate-500">{r.source} · {date(r.joined_at)} · {r.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="mb-2 font-semibold">{t("Commissions")}</p>
              {!d.commissions.length ? <p className="text-slate-500">{t("None yet.")}</p> : (
                <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {d.commissions.map((c) => (
                    <li key={c.id} className="flex items-center gap-2 px-3 py-2">
                      <span className="flex-1">{c.workspace} <span className="text-xs text-slate-500">· {date(c.created_at)} · {c.state}</span></span>
                      <span className="tabular-nums">{money(c.amount, c.currency)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminAffiliatesPage() {
  const { me } = useMe();
  const t = useT();
  const [list, setList] = useState<AdminAffiliateList | null>(null);
  const [payouts, setPayouts] = useState<AffiliatePayout[] | null>(null);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { const timer = setTimeout(() => setDebounced(q), 300); return () => clearTimeout(timer); }, [q]);
  const load = useCallback(() => {
    Api.platformAffiliates({ status, q: debounced }).then(setList).catch((e) => setError(e.message));
    Api.platformAffiliatePayouts("requested").then(setPayouts).catch((e) => setError(e.message));
  }, [status, debounced]);
  useEffect(() => { load(); }, [load]);

  if (!me.user.is_platform_admin) {
    return <div className="p-8 text-sm text-slate-600">{t("Only OmniInbox platform admins can open this page.")}</div>;
  }
  const s = list?.summary;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <Link href="/admin-panel" className="mb-1 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"><ArrowLeft size={13} /> {t("Platform admin")}</Link>
            <h1 className="flex items-center gap-2 text-xl font-semibold"><Gift size={20} className="text-brand-600" /> {t("Affiliates")}</h1>
            <p className="text-sm text-slate-600">{t("Approve affiliates, see what they've brought in, and pay out their commissions.")}</p>
          </div>
          <button className="btn-secondary" onClick={load}><RotateCcw size={15} /> {t("Refresh")}</button>
        </div>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        {!s ? <div className="flex justify-center p-10 text-slate-400"><LoaderCircle className="animate-spin" /></div> : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Waiting for approval" value={s.pending_applications} tone={s.pending_applications ? "warn" : undefined} sub={t(s.active === 1 ? "{n} active affiliate" : "{n} active affiliates", { n: s.active })} />
            <Tile label="Payouts to send" value={s.payouts_requested} tone={s.payouts_requested ? "warn" : undefined} />
            <Tile label="Commission owed" value={both(s.owed)} sub={t("Paid so far: {amount}", { amount: both(s.paid_all_time) })} />
            <Tile label="Revenue from referrals" value={both(s.referred_revenue)} />
          </div>
        )}

        {!!payouts?.length && (
          <div className="card overflow-hidden">
            <h2 className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 font-semibold"><Send size={16} className="text-brand-600" /> {t("Payout requests")}</h2>
            <p className="px-4 pt-3 text-xs text-slate-500">{t("Send the money by eSewa, Khalti or bank, then enter the transaction ID and mark it paid. The affiliate gets an email.")}</p>
            <ul className="divide-y divide-slate-100">{payouts.map((p) => <PayoutRow key={p.id} p={p} onDone={load} />)}</ul>
          </div>
        )}

        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-3">
            <div className="flex flex-wrap gap-1">
              {FILTERS.map(([key, label]) => (
                <button key={key} onClick={() => setStatus(key)}
                  className={clsx("rounded-full px-3 py-1 text-xs font-medium", status === key ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}>{t(label)}</button>
              ))}
            </div>
            <div className="relative ml-auto w-full sm:w-64">
              <Search size={15} className="absolute left-3 top-2.5 text-slate-400" />
              <input className="input py-1.5 pl-8 text-sm" placeholder={t("Code, name or email")} value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("Affiliate")}</th><th className="px-3 py-2 font-medium">{t("Code")}</th>
                  <th className="px-3 py-2 font-medium">{t("Status")}</th><th className="px-3 py-2 text-right font-medium">{t("Rate")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("Sign-ups")}</th><th className="px-3 py-2 text-right font-medium">{t("Paying")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("Earned")}</th><th className="px-3 py-2 text-right font-medium">{t("Owed")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {!list && <tr><td colSpan={8} className="p-6 text-center text-slate-400"><LoaderCircle className="mx-auto animate-spin" /></td></tr>}
                {list?.results.length === 0 && <tr><td colSpan={8} className="p-6 text-center text-slate-500">{t("No affiliates yet.")}</td></tr>}
                {list?.results.map((a) => (
                  <tr key={a.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(a.id)}>
                    <td className="px-3 py-2.5"><p className="font-medium text-slate-900">{a.name}</p><p className="text-xs text-slate-500">{a.email} · {date(a.created_at)}</p></td>
                    <td className="px-3 py-2.5 font-mono text-xs">{a.code}</td>
                    <td className="px-3 py-2.5"><span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_STYLE[a.status])}>{t(STATUS_LABEL[a.status])}</span></td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{pct(a.rate)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{a.signups}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{a.paying}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{both(a.lifetime)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{both(a.owed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {open !== null && <Drawer id={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}
