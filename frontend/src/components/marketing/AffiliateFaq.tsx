"use client";

import { useAffiliateProgram } from "@/components/marketing/AffiliateSection";

export default function AffiliateFaq() {
  const { program, pct } = useAffiliateProgram();
  const min = `Rs ${Number(program.min_payout.NPR).toLocaleString("en-IN")}`;
  const items = [
    ["Who can join?", "Anyone with an OmniInbox account: creators, agencies, consultants, or happy customers. Apply from your account, and we review applications within 1-2 days."],
    ["How much do I earn?", `${pct}% of every payment a business you referred makes: monthly or yearly, on every renewal, for as long as they stay subscribed. If they upgrade, you earn more.`],
    ["How do referrals get tracked?", "Through your personal link (remembered for 60 days after the click) or your promo code, which they can type at sign-up or on the Billing page before their first payment. Once a business is linked to you, it stays yours."],
    ["When do I get paid?", `Each commission is held ${program.hold_days} days in case of a refund, then becomes available. Request a withdrawal once you have ${min}, and we send it to your eSewa, Khalti or bank account within a few working days.`],
    ["Can I use my own code?", "No. Commissions are for bringing in new businesses, so your own workspace doesn't count."],
    ["Where do I see my earnings?", "Your affiliate dashboard shows link clicks, sign-ups, paying customers, every commission and your payouts."],
  ];
  return (
    <dl className="mt-10 divide-y divide-slate-200 border-y border-slate-200">
      {items.map(([q, a]) => (
        <div key={q} className="py-5">
          <dt className="font-semibold text-slate-900">{q}</dt>
          <dd className="mt-2 text-sm text-slate-600">{a}</dd>
        </div>
      ))}
    </dl>
  );
}
