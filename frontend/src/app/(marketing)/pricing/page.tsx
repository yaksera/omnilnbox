import type { Metadata } from "next";
import Link from "next/link";
import { CreditCard, ShieldCheck, Wallet } from "lucide-react";
import PricingPlans, { ComparisonTable } from "@/components/marketing/Pricing";
import Faq from "@/components/marketing/Faq";

export const metadata: Metadata = {
  title: "Pricing | OmniInbox",
  description: "Plans for every team size. Pay in NPR with Khalti or eSewa, or in USD by card. 14-day free trial.",
};

export default function PricingPage() {
  return (
    <>
      <section className="bg-white">
        <div className="mx-auto max-w-6xl px-4 pb-16 pt-14 sm:px-6">
          <div className="mx-auto mb-10 max-w-2xl text-center">
            <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">Pricing</p>
            <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">Plans for every team</h1>
            <p className="mt-4 text-lg text-slate-600">Start with a 14-day free trial of Pro. No credit card required.</p>
          </div>
          <PricingPlans />
          <div className="mt-10 grid gap-4 sm:grid-cols-3">
            {[
              { icon: Wallet, title: "Khalti & eSewa", text: "Pay in Nepali rupees from your wallet." },
              { icon: CreditCard, title: "Cards via Stripe", text: "Visa, Mastercard and more, in US dollars." },
              { icon: ShieldCheck, title: "No lock-in", text: "Prepaid monthly or yearly. Downgrade any time." },
            ].map((b) => (
              <div key={b.title} className="flex gap-3 rounded-xl border border-slate-200 p-4">
                <b.icon className="shrink-0 text-brand-600" size={22} />
                <div><p className="text-sm font-semibold text-slate-900">{b.title}</p><p className="text-sm text-slate-600">{b.text}</p></div>
              </div>
            ))}
          </div>
        </div>
      </section>
      <section className="bg-slate-50">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="mb-6 text-2xl font-bold text-slate-900">Compare features</h2>
          <ComparisonTable />
          <div className="mt-8 flex flex-col items-start justify-between gap-4 rounded-2xl bg-slate-950 p-6 text-white sm:flex-row sm:items-center">
            <div>
              <p className="text-lg font-semibold">Need more than 25 channels or custom terms?</p>
              <p className="text-sm text-slate-300">Enterprise includes custom limits, onboarding, invoicing and an SLA.</p>
            </div>
            <Link href="/contact" className="btn bg-white text-slate-900 hover:bg-slate-100">Contact sales</Link>
          </div>
        </div>
      </section>
      <section className="bg-white">
        <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
          <h2 className="mb-6 text-2xl font-bold text-slate-900">Billing questions</h2>
          <Faq />
        </div>
      </section>
    </>
  );
}
