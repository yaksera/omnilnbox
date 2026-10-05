"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import Link from "next/link";
import { BadgePercent, Check, CircleAlert, CircleCheck, CreditCard, Gift, LoaderCircle, Minus, Plus, Sparkles, Wallet, X } from "lucide-react";
import { Api } from "@/lib/api";
import type { Billing, Catalog } from "@/lib/types";
import { type Currency, daysLeft, money } from "@/lib/money";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const GATEWAY_UI = {
  khalti: { label: "Khalti", sub: "Wallet", currency: "NPR", color: "#5C2D91", icon: Wallet },
  esewa: { label: "eSewa", sub: "Wallet", currency: "NPR", color: "#60BB46", icon: Wallet },
  stripe: { label: "Card", sub: "Visa / Mastercard", currency: "USD", color: "#635BFF", icon: CreditCard },
} as const;

const CYCLE_LABELS = { monthly: "Monthly", yearly: "Yearly" } as const;
const PAYMENT_STATUS_LABELS: Record<string, string> = { pending: "Pending", paid: "Paid", failed: "Failed" };

function Meter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = Math.min(100, Math.round((used / Math.max(limit, 1)) * 100));
  return (
    <div>
      <div className="flex justify-between text-sm"><span className="text-slate-600">{label}</span><span className="font-medium text-slate-900">{used} / {limit >= 1000 ? "∞" : limit}</span></div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={clsx("h-full rounded-full", pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-500" : "bg-brand-600")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function BillingPage() {
  const t = useT();
  const { me, reloadMe } = useMe();
  const [billing, setBilling] = useState<Billing | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [plan, setPlan] = useState("pro");
  const [cycle, setCycle] = useState<"monthly" | "yearly">("yearly");
  const [gateway, setGateway] = useState<string>("");
  const [extraSeats, setExtraSeats] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ kind: "success" | "failed"; text: string } | null>(null);
  const [promo, setPromo] = useState("");
  const [promoState, setPromoState] = useState<{ busy: boolean; error: string }>({ busy: false, error: "" });

  async function applyPromo(e: React.FormEvent) {
    e.preventDefault();
    setPromoState({ busy: true, error: "" });
    try {
      const r = await Api.addPromoCode(promo.trim());
      setBilling((b) => (b ? { ...b, promo_code: r.code, can_add_promo_code: false } : b));
      setPromo("");
      setPromoState({ busy: false, error: "" });
    } catch (err) {
      setPromoState({ busy: false, error: err instanceof Error ? err.message : t("Couldn't apply the code") });
    }
  }

  useEffect(() => {
    Promise.all([Api.billing(), Api.plans()]).then(([b, c]) => {
      setBilling(b);
      setCatalog(c);
      setGateway(b.gateways[0]?.key ?? "");
      if (["starter", "pro", "business"].includes(b.plan) && !b.is_trialing) setPlan(b.plan);
    });
    const q = new URLSearchParams(window.location.search);
    if (q.get("payment") === "success") {
      setResult({ kind: "success", text: "Payment received. Your plan is active." });
      reloadMe();
    } else if (q.get("payment") === "failed") {
      setResult({ kind: "failed", text: q.get("message") || "The payment was not completed. You have not been charged." });
    }
    if (q.get("payment")) window.history.replaceState(null, "", "/billing");
  }, [reloadMe]);

  const currency: Currency = (billing?.gateways.find((g) => g.key === gateway)?.currency ?? "NPR") as Currency;
  const selected = catalog?.plans.find((p) => p.key === plan);
  const total = useMemo(() => {
    if (!selected?.prices || !catalog) return 0;
    // Same formula as the backend (billing/plans.py price_for) so the shown total matches the charge
    const monthly = selected.prices[currency].monthly + catalog.extra_seat[currency] * extraSeats;
    const raw = cycle === "yearly" ? monthly * 12 * (1 - catalog.yearly_discount) : monthly;
    return currency === "NPR" ? Math.round(raw) : Math.round(raw * 100) / 100;
  }, [selected, catalog, currency, cycle, extraSeats]);

  if (!billing || !catalog) return <div className="flex h-full items-center justify-center text-slate-400"><LoaderCircle className="animate-spin" /></div>;

  async function checkout() {
    setBusy(true);
    setError("");
    try {
      const r = await Api.checkout({ plan, cycle, gateway, extra_seats: extraSeats });
      if (r.redirect_url) {
        window.location.href = r.redirect_url;
        return;
      }
      if (r.form_url && r.fields) {
        // eSewa needs a real browser form POST
        const form = Object.assign(document.createElement("form"), { method: "POST", action: r.form_url });
        for (const [k, v] of Object.entries(r.fields)) {
          form.appendChild(Object.assign(document.createElement("input"), { type: "hidden", name: k, value: v }));
        }
        document.body.appendChild(form);
        form.submit();
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn’t start checkout"));
    }
    setBusy(false);
  }

  const paidPlans = catalog.plans.filter((p) => ["starter", "pro", "business"].includes(p.key));
  const statusLine = billing.is_trialing
    ? t("Free trial · {n} days left", { n: daysLeft(billing.trial_ends_at) })
    : billing.is_expired ? t("Expired, so Free plan limits apply")
      : billing.effective_plan === "free" ? t("Free forever")
        : t(billing.billing_cycle === "yearly" ? "Renews / ends {date} · billed yearly" : "Renews / ends {date} · billed monthly",
          { date: new Date(billing.plan_expires_at!).toLocaleDateString(undefined, { dateStyle: "medium" }) });

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
        <div>
          <h1 className="text-2xl font-bold">{t("Billing")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t("Manage your plan, seats and payments for {name}.", { name: me.workspace.name })}</p>
        </div>

        {result && (
          <div className={clsx("flex items-start gap-2 rounded-lg px-4 py-3 text-sm", result.kind === "success" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800")}>
            {result.kind === "success" ? <CircleCheck size={18} /> : <CircleAlert size={18} />}
            <span className="flex-1">{t(result.text)}</span>
            <button onClick={() => setResult(null)} aria-label={t("Dismiss")}><X size={16} /></button>
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("Current plan")}</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2 className="text-2xl font-bold">{billing.plan_name}</h2>
              {billing.is_trialing && <span className="rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-semibold text-brand-700">{t("Trial")}</span>}
              {billing.is_expired && <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">{t("Expired")}</span>}
            </div>
            <p className="mt-1 text-sm text-slate-600">{statusLine}</p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <Meter label={t("Connected channels")} used={billing.usage.channels} limit={billing.limits.channels} />
              <Meter label={t("Team seats (incl. pending invites)")} used={billing.usage.seats} limit={billing.limits.seats} />
            </div>
          </div>
          <div className="card p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("Included features")}</p>
            <ul className="mt-3 space-y-2 text-sm">
              {Object.entries(catalog.feature_labels).map(([k, label]) => (
                <li key={k} className={clsx("flex items-center gap-2", billing.features.includes(k) ? "text-slate-800" : "text-slate-400")}>
                  {billing.features.includes(k) ? <Check size={16} className="text-emerald-600" /> : <Minus size={16} />} {t(label)}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {billing.can_manage && (billing.promo_code || billing.can_add_promo_code) && (
          <div className="card flex flex-col gap-3 p-5 sm:flex-row sm:items-center">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"><BadgePercent size={20} /></span>
            {billing.promo_code ? (
              <p className="flex-1 text-sm text-slate-700">{t("Promo code {code} is applied to this workspace.", { code: billing.promo_code })}</p>
            ) : (
              <form onSubmit={applyPromo} className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
                <div className="flex-1">
                  <p className="text-sm font-medium text-slate-800">{t("Have a promo code?")}</p>
                  <p className="text-xs text-slate-500">{t("Add it before your first payment.")}</p>
                  {promoState.error && <p className="mt-1 text-xs text-red-600">{t(promoState.error)}</p>}
                </div>
                <input className="input uppercase sm:w-40" value={promo} maxLength={20} placeholder="RAM2026"
                  onChange={(e) => setPromo(e.target.value.replace(/[^A-Za-z0-9]/g, "").toUpperCase())} />
                <button className="btn-secondary" disabled={promoState.busy || promo.length < 4}>
                  {promoState.busy && <LoaderCircle className="animate-spin" size={16} />} {t("Apply")}
                </button>
              </form>
            )}
          </div>
        )}

        {billing.can_manage ? (
          <div className="card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">{billing.effective_plan === "free" || billing.is_trialing ? t("Choose a plan") : t("Change or renew plan")}</h2>
              <div className="inline-flex rounded-lg bg-slate-100 p-1 text-sm">
                {(["monthly", "yearly"] as const).map((c) => (
                  <button key={c} onClick={() => setCycle(c)} className={clsx("rounded-md px-3 py-1.5 font-medium", cycle === c ? "bg-white shadow-sm" : "text-slate-600")}>
                    {t(CYCLE_LABELS[c])}{c === "yearly" && <span className="ml-1 text-xs text-emerald-600">-20%</span>}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-3">
              {paidPlans.map((p) => {
                const price = p.prices![currency];
                const tooSmall = billing.usage.channels > p.channels;
                return (
                  <button key={p.key} disabled={tooSmall} onClick={() => setPlan(p.key)}
                    className={clsx("relative rounded-xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-50",
                      plan === p.key ? "border-brand-500 ring-2 ring-brand-500" : "border-slate-200 hover:border-slate-300")}>
                    {p.popular && <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold text-white"><Sparkles size={10} /> {t("Popular")}</span>}
                    <p className="font-semibold">{p.name}</p>
                    <p className="mt-1 text-xl font-bold">{money(cycle === "yearly" ? price.yearly_per_month : price.monthly, currency, { compact: true })}<span className="text-sm font-normal text-slate-500">{t("/mo")}</span></p>
                    <p className="mt-1 text-xs text-slate-500">{t("{channels} channels · {seats} seats · {credits} AI credits", { channels: p.channels, seats: p.seats, credits: p.ai_credits.toLocaleString() })}</p>
                    {tooSmall && <p className="mt-1 text-xs text-red-600">{t("You use more channels than this plan allows")}</p>}
                    {me.workspace.plan === p.key && !billing.is_trialing && !billing.is_expired && <p className="mt-1 text-xs font-medium text-emerald-700">{t("Current plan")}</p>}
                  </button>
                );
              })}
            </div>

            <div className="mt-6 grid gap-6 md:grid-cols-2">
              <div>
                <p className="text-sm font-medium text-slate-700">{t("Extra seats")}</p>
                <p className="text-xs text-slate-500">{t("{price} per seat per month, on top of the plan’s {n} seats.", { price: money(catalog.extra_seat[currency], currency), n: selected?.seats ?? 0 })}</p>
                <div className="mt-2 inline-flex items-center rounded-lg border border-slate-300">
                  <button className="px-3 py-2 text-slate-600 disabled:opacity-40" onClick={() => setExtraSeats(Math.max(0, extraSeats - 1))} disabled={extraSeats === 0} aria-label={t("Fewer seats")}><Minus size={16} /></button>
                  <span className="w-10 text-center font-semibold">{extraSeats}</span>
                  <button className="px-3 py-2 text-slate-600" onClick={() => setExtraSeats(Math.min(100, extraSeats + 1))} aria-label={t("More seats")}><Plus size={16} /></button>
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-700">{t("Payment method")}</p>
                {billing.gateways.length === 0 ? (
                  <p className="mt-2 text-sm text-amber-700">{t("No payment method is configured yet. Add your Khalti, eSewa or Stripe keys to the backend .env.")}</p>
                ) : (
                  <div className="mt-2 grid gap-2 sm:grid-cols-3">
                    {billing.gateways.map((g) => {
                      const ui = GATEWAY_UI[g.key];
                      return (
                        <button key={g.key} onClick={() => setGateway(g.key)}
                          className={clsx("rounded-lg border p-3 text-left transition", gateway === g.key ? "border-brand-500 ring-2 ring-brand-500" : "border-slate-200 hover:border-slate-300")}>
                          <span className="flex items-center gap-2 font-semibold" style={{ color: ui.color }}><ui.icon size={16} /> {t(ui.label)}</span>
                          <span className="text-xs text-slate-500">{t(ui.sub)} · {ui.currency}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            <div className="mt-6 flex flex-col gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm text-slate-600">{cycle === "yearly" ? t("Total for 1 year") : t("Total for 1 month")}</p>
                <p className="text-2xl font-bold">{money(total, currency)}</p>
                <p className="text-xs text-slate-500">{t("Prepaid. Renewing the same plan adds time to your current period.")}</p>
              </div>
              <div className="flex flex-col items-stretch gap-2 sm:items-end">
                {error && <p className="text-sm text-red-600">{error}</p>}
                <button className="btn-primary px-6 py-2.5" onClick={checkout} disabled={busy || !gateway}>
                  {busy && <LoaderCircle className="animate-spin" size={16} />} {t("Pay {amount}", { amount: money(total, currency) })}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="card p-5 text-sm text-slate-600">{t("Only the workspace owner can change the plan or see invoices.")}</div>
        )}

        <Link href="/affiliate" className="card flex items-center gap-3 p-4 text-sm hover:border-brand-300">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><Gift size={18} /></span>
          <span className="flex-1">
            <span className="block font-medium text-slate-800">{t("Refer businesses, earn every month")}</span>
            <span className="text-slate-500">{t("Share your link or promo code and earn a commission on every payment they make, for as long as they stay subscribed.")}</span>
          </span>
        </Link>

        {billing.can_manage && billing.payments.length > 0 && (
          <div className="card overflow-hidden">
            <h2 className="border-b border-slate-100 px-5 py-3 font-semibold">{t("Payment history")}</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr><th className="px-5 py-2">{t("Date")}</th><th className="px-5 py-2">{t("Plan")}</th><th className="px-5 py-2">{t("Method")}</th><th className="px-5 py-2">{t("Amount")}</th><th className="px-5 py-2">{t("Status")}</th><th className="px-5 py-2">{t("Period ends")}</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {billing.payments.map((p) => (
                    <tr key={p.id}>
                      <td className="px-5 py-2.5">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="px-5 py-2.5"><span className="capitalize">{p.plan}</span> · {t(CYCLE_LABELS[p.cycle as keyof typeof CYCLE_LABELS] ?? p.cycle)}</td>
                      <td className="px-5 py-2.5">{t(GATEWAY_UI[p.gateway as keyof typeof GATEWAY_UI]?.label ?? p.gateway)}</td>
                      <td className="px-5 py-2.5 font-medium">{money(p.amount, p.currency as Currency)}</td>
                      <td className="px-5 py-2.5">
                        <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium",
                          p.status === "paid" ? "bg-emerald-50 text-emerald-700" : p.status === "failed" ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-600")}
                          title={p.failure_reason}>{t(PAYMENT_STATUS_LABELS[p.status] ?? p.status)}</span>
                      </td>
                      <td className="px-5 py-2.5">{p.period_end ? new Date(p.period_end).toLocaleDateString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
