"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { ArrowRight, Gift, Link2, Repeat, Users, Wallet } from "lucide-react";
import { Api, auth } from "@/lib/api";

type Program = { rate: string; hold_days: number; min_payout: { NPR: string; USD: string } };
type PlanPrice = { key: string; name: string; price: number };

// Used until the API answers (and if it can't be reached)
const FALLBACK_PROGRAM: Program = { rate: "0.20", hold_days: 14, min_payout: { NPR: "2000", USD: "15" } };
const FALLBACK_PLANS: PlanPrice[] = [
  { key: "starter", name: "Starter", price: 1499 }, { key: "pro", name: "Pro", price: 3999 }, { key: "business", name: "Business", price: 8999 },
];

const rs = (n: number) => `Rs ${Math.round(n).toLocaleString("en-IN")}`;

/** Where "Become an affiliate" goes: the dashboard if logged in, otherwise sign-up then the dashboard. */
export function useAffiliateCta() {
  const [href, setHref] = useState("/register?next=/affiliate");
  useEffect(() => { if (auth.isLoggedIn()) setHref("/affiliate"); }, []);
  return href;
}

export function useAffiliateProgram() {
  const [program, setProgram] = useState<Program>(FALLBACK_PROGRAM);
  const [plans, setPlans] = useState<PlanPrice[]>(FALLBACK_PLANS);
  useEffect(() => {
    Api.affiliateProgram().then(setProgram).catch(() => undefined);
    Api.plans().then((c) => {
      const paid = c.plans.filter((p) => p.prices && ["starter", "pro", "business"].includes(p.key))
        .map((p) => ({ key: p.key, name: p.name, price: p.prices!.NPR.monthly }));
      if (paid.length) setPlans(paid);
    }).catch(() => undefined);
  }, []);
  return { program, plans, pct: Math.round(Number(program.rate) * 100) };
}

function Calculator({ pct, plans }: { pct: number; plans: PlanPrice[] }) {
  const [shops, setShops] = useState(10);
  const [planKey, setPlanKey] = useState("pro");
  const plan = plans.find((p) => p.key === planKey) ?? plans[0];
  const monthly = shops * plan.price * (pct / 100);
  return (
    <div className="rounded-2xl bg-white p-6 text-slate-900 shadow-xl ring-1 ring-slate-200">
      <p className="text-sm font-semibold text-slate-500">Estimate your earnings</p>
      <label className="mt-5 block">
        <span className="flex items-baseline justify-between text-sm font-medium text-slate-700">
          Businesses you refer <span className="text-2xl font-bold tabular-nums text-slate-900">{shops}</span>
        </span>
        <input type="range" min={1} max={100} value={shops} onChange={(e) => setShops(Number(e.target.value))}
          className="mt-2 w-full accent-brand-600" aria-label="Businesses you refer" />
      </label>
      <div className="mt-4">
        <span className="text-sm font-medium text-slate-700">Their plan</span>
        <div className="mt-2 grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1 text-sm">
          {plans.map((p) => (
            <button key={p.key} type="button" onClick={() => setPlanKey(p.key)}
              className={clsx("rounded-md px-2 py-1.5 font-medium", planKey === p.key ? "bg-white shadow-sm" : "text-slate-600")}>
              {p.name}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-slate-500">{plan.name} is {rs(plan.price)} per month</p>
      </div>
      <div className="mt-6 rounded-xl bg-brand-50 p-4">
        <p className="text-sm text-brand-700">You earn</p>
        <p className="text-3xl font-bold tabular-nums text-brand-700">{rs(monthly)}<span className="text-base font-medium"> / month</span></p>
        <p className="mt-1 text-sm text-slate-600">{rs(monthly * 12)} a year, every year they stay subscribed</p>
      </div>
    </div>
  );
}

export default function AffiliateSection({ showLearnMore = true }: { showLearnMore?: boolean }) {
  const { program, plans, pct } = useAffiliateProgram();
  const cta = useAffiliateCta();
  const steps = [
    { icon: Link2, title: "Share your link or code", text: "Post it on Facebook, TikTok or YouTube, or send it to shops you know." },
    { icon: Users, title: "They subscribe", text: "They sign up through your link, or type your promo code at sign-up." },
    { icon: Repeat, title: `Earn ${pct}% every month`, text: "On every payment they make, for as long as they stay subscribed. Not just the first one." },
    { icon: Wallet, title: "Get paid in Nepal", text: `Withdraw to eSewa, Khalti or your bank once you have ${rs(Number(program.min_payout.NPR))}.` },
  ];
  return (
    <section id="affiliates" className="scroll-mt-20 bg-slate-950">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-indigo-200">
            <Gift size={14} /> Affiliate program
          </span>
          <h2 className="mt-4 text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Earn {pct}% every month for every business you refer
          </h2>
          <p className="mt-4 text-lg text-slate-300">
            Know shop owners, run a business page or make content for sellers? Recommend OmniInbox and earn a
            recurring commission for life, not a one-time bonus.
          </p>
          <div className="mt-8 grid gap-5 sm:grid-cols-2">
            {steps.map((s) => (
              <div key={s.title} className="flex gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-indigo-300"><s.icon size={18} /></span>
                <div>
                  <p className="font-semibold text-white">{s.title}</p>
                  <p className="mt-1 text-sm text-slate-400">{s.text}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href={cta} className="btn bg-white px-5 py-2.5 text-brand-700 hover:bg-indigo-50">Become an affiliate <ArrowRight size={16} /></Link>
            {showLearnMore && <Link href="/affiliates" className="btn px-4 py-2.5 text-slate-200 hover:bg-white/10">How it works</Link>}
          </div>
          <p className="mt-3 text-xs text-slate-500">Free to join. Applications are reviewed within 1-2 days.</p>
        </div>
        <Calculator pct={pct} plans={plans} />
      </div>
    </section>
  );
}
