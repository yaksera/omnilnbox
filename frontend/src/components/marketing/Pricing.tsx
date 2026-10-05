"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import clsx from "clsx";
import { Check, LoaderCircle, Minus, Sparkles } from "lucide-react";
import { Api } from "@/lib/api";
import type { Catalog, Plan } from "@/lib/types";
import { type Currency, money } from "@/lib/money";

export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    Api.plans().then(setCatalog).catch(() => setError(true));
  }, []);
  return { catalog, error };
}

export function Toggles({ currency, setCurrency, cycle, setCycle, discount }: {
  currency: Currency; setCurrency: (c: Currency) => void;
  cycle: "monthly" | "yearly"; setCycle: (c: "monthly" | "yearly") => void; discount: number;
}) {
  const seg = (active: boolean) =>
    clsx("rounded-md px-3.5 py-1.5 text-sm font-medium transition", active ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900");
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      <div className="inline-flex rounded-lg bg-slate-100 p-1" role="group" aria-label="Billing cycle">
        <button className={seg(cycle === "monthly")} onClick={() => setCycle("monthly")}>Monthly</button>
        <button className={seg(cycle === "yearly")} onClick={() => setCycle("yearly")}>
          Yearly <span className="ml-1 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700">-{Math.round(discount * 100)}%</span>
        </button>
      </div>
      <div className="inline-flex rounded-lg bg-slate-100 p-1" role="group" aria-label="Currency">
        <button className={seg(currency === "NPR")} onClick={() => setCurrency("NPR")}>NPR (Rs.)</button>
        <button className={seg(currency === "USD")} onClick={() => setCurrency("USD")}>USD ($)</button>
      </div>
    </div>
  );
}

function PlanCard({ plan, catalog, currency, cycle }: { plan: Plan; catalog: Catalog; currency: Currency; cycle: "monthly" | "yearly" }) {
  const price = plan.prices?.[currency];
  const perMonth = price ? (cycle === "yearly" ? price.yearly_per_month : price.monthly) : null;
  const cta = plan.key === "enterprise"
    ? { href: "/contact", label: "Contact sales" }
    : plan.key === "free" ? { href: "/register", label: "Start for free" } : { href: `/register?plan=${plan.key}`, label: `Start ${catalog.trial_days}-day trial` };
  return (
    <div className={clsx("relative flex flex-col rounded-2xl border bg-white p-6",
      plan.popular ? "border-brand-500 shadow-xl shadow-brand-500/10 ring-1 ring-brand-500" : "border-slate-200")}>
      {plan.popular && (
        <span className="absolute -top-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-full bg-brand-600 px-3 py-1 text-xs font-semibold text-white">
          <Sparkles size={12} /> Most popular
        </span>
      )}
      <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
      <p className="mt-1 min-h-[40px] text-sm text-slate-600">{plan.tagline}</p>
      <div className="mt-5 min-h-[64px]">
        {perMonth === null ? (
          <p className="text-3xl font-bold tracking-tight text-slate-900">Custom</p>
        ) : (
          <>
            <p className="flex items-baseline gap-1">
              <span className="text-3xl font-bold tracking-tight text-slate-900">{money(perMonth, currency, { compact: true })}</span>
              <span className="text-sm text-slate-500">/month</span>
            </p>
            {cycle === "yearly" && price && price.yearly > 0 && (
              <p className="mt-1 text-xs text-slate-500">{money(price.yearly, currency)} billed yearly</p>
            )}
          </>
        )}
      </div>
      <Link href={cta.href} className={clsx("mt-5 w-full", plan.popular ? "btn-primary" : "btn-secondary")}>{cta.label}</Link>
      <ul className="mt-6 space-y-2.5 text-sm text-slate-700">
        <li className="flex gap-2"><Check size={17} className="mt-0.5 shrink-0 text-brand-600" />{plan.key === "enterprise" ? "Unlimited" : plan.channels} connected channels</li>
        <li className="flex gap-2"><Check size={17} className="mt-0.5 shrink-0 text-brand-600" />{plan.key === "enterprise" ? "Unlimited" : plan.seats} team {plan.seats === 1 ? "seat" : "seats"}</li>
        <li className="flex gap-2"><Check size={17} className="mt-0.5 shrink-0 text-brand-600" />{plan.history_days ? `${plan.history_days}-day` : "Unlimited"} message history</li>
        <li className="flex gap-2"><Check size={17} className="mt-0.5 shrink-0 text-brand-600" />{plan.ai_credits.toLocaleString()} AI credits / month</li>
        {plan.features.slice(0, 6).map((f) => (
          <li key={f} className="flex gap-2"><Check size={17} className="mt-0.5 shrink-0 text-brand-600" />{catalog.feature_labels[f]}</li>
        ))}
      </ul>
    </div>
  );
}

export default function PricingPlans({ showToggles = true }: { showToggles?: boolean }) {
  const { catalog, error } = useCatalog();
  const [currency, setCurrency] = useState<Currency>("NPR");
  const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");

  if (error) return <p className="text-center text-sm text-slate-500">Pricing is temporarily unavailable. Please refresh.</p>;
  if (!catalog) return <div className="flex justify-center py-16 text-slate-400"><LoaderCircle className="animate-spin" /></div>;

  const plans = catalog.plans.filter((p) => p.key !== "free");
  return (
    <div>
      {showToggles && <Toggles currency={currency} setCurrency={setCurrency} cycle={cycle} setCycle={setCycle} discount={catalog.yearly_discount} />}
      <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {plans.map((p) => <PlanCard key={p.key} plan={p} catalog={catalog} currency={currency} cycle={cycle} />)}
      </div>
      <p className="mt-6 text-center text-sm text-slate-500">
        Just exploring? The <Link href="/register" className="font-medium text-brand-600">Free plan</Link> includes 2 channels and 1 seat, forever.
        {" "}Extra seats: {money(catalog.extra_seat[currency], currency)}/seat/month.
      </p>
    </div>
  );
}

export function ComparisonTable() {
  const { catalog } = useCatalog();
  if (!catalog) return null;
  const plans = catalog.plans;
  const rows: Array<[string, (p: Plan) => React.ReactNode]> = [
    ["Connected channels", (p) => (p.key === "enterprise" ? "Unlimited" : p.channels)],
    ["Team seats", (p) => (p.key === "enterprise" ? "Unlimited" : p.seats)],
    ["Message history", (p) => (p.history_days ? `${p.history_days} days` : "Unlimited")],
    ["AI credits / month", (p) => p.ai_credits.toLocaleString()],
    ["All 9 platforms", () => true],
    ["Unified inbox, assignment, open/closed", () => true],
  ];
  const feats = Object.keys(catalog.feature_labels);
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-4 py-3 text-left font-semibold text-slate-900">Compare plans</th>
            {plans.map((p) => <th key={p.key} className={clsx("px-4 py-3 text-center font-semibold", p.popular ? "text-brand-700" : "text-slate-900")}>{p.name}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {[...rows, ...feats.map((f) => [catalog.feature_labels[f], (p: Plan) => p.features.includes(f)] as [string, (p: Plan) => React.ReactNode])].map(([label, fn]) => (
            <tr key={label}>
              <td className="px-4 py-3 text-slate-700">{label}</td>
              {plans.map((p) => {
                const v = fn(p);
                return (
                  <td key={p.key} className="px-4 py-3 text-center text-slate-700">
                    {v === true ? <Check size={17} className="mx-auto text-brand-600" aria-label="Included" />
                      : v === false ? <Minus size={17} className="mx-auto text-slate-300" aria-label="Not included" />
                        : <Fragment>{v}</Fragment>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
