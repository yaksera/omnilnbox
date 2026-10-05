import type { Metadata } from "next";
import AffiliateSection from "@/components/marketing/AffiliateSection";
import AffiliateFaq from "@/components/marketing/AffiliateFaq";

export const metadata: Metadata = {
  title: "Affiliate program — OmniInbox",
  description: "Earn a recurring commission every month for every business you refer to OmniInbox. Paid to eSewa, Khalti or your bank.",
};

export default function AffiliatesPage() {
  return (
    <>
      <AffiliateSection showLearnMore={false} />
      <section className="bg-white">
        <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
          <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">Affiliate questions</h2>
          <AffiliateFaq />
        </div>
      </section>
    </>
  );
}
