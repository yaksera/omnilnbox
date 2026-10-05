import type { Metadata } from "next";
import Legal from "@/components/marketing/Legal";

export const metadata: Metadata = { title: "Terms of Service | OmniInbox" };

export default function Terms() {
  return (
    <Legal title="Terms of Service" updated="30 September 2026" sections={[
      ["Agreement", "By creating an account or using OmniInbox (the \"Service\") you agree to these Terms on behalf of yourself and the organisation you represent (the \"Customer\")."],
      ["The Service", "OmniInbox lets teams receive and reply to messages from third-party platforms such as WhatsApp, Instagram, Messenger, TikTok, Telegram, Discord and email providers in one inbox. Access to each platform depends on that platform's own terms, approvals and availability, which are outside our control."],
      ["Accounts and roles", "The workspace owner is responsible for the account, for everyone they invite, and for keeping credentials secure. Owners and admins decide which teammates have access and what role they hold."],
      ["Customer data", "Messages, contacts and files you process through the Service remain yours. You are responsible for having a lawful basis to process your customers' data and for complying with the policies of each connected platform, including messaging-window and opt-in rules."],
      ["Acceptable use", "You may not use the Service to send spam, unlawful or harmful content, to harass anyone, or to attempt to access other workspaces, our infrastructure or third-party systems without authorisation."],
      ["Plans, trials and payment", "Paid plans are prepaid for the selected period (monthly or yearly) and payable through Khalti, eSewa or Stripe. Trials last 14 days. If a plan is not renewed, the workspace moves to the Free plan and its limits apply; your data is retained. Fees are non-refundable except where required by law."],
      ["Availability and changes", "We work to keep the Service available but do not guarantee uninterrupted operation. We may update features and these Terms; material changes will be announced in the app or by email."],
      ["Termination", "You may stop using the Service at any time. We may suspend accounts that breach these Terms. On request we will delete your workspace data, subject to legal retention obligations."],
      ["Liability", "To the extent permitted by law, the Service is provided \"as is\" and our total liability is limited to the fees you paid in the 12 months before the claim."],
      ["Contact", "Questions about these Terms: legal@omniinbox.app"],
    ]} />
  );
}
