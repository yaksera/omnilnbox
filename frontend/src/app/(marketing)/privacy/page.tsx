import type { Metadata } from "next";
import Legal from "@/components/marketing/Legal";

export const metadata: Metadata = { title: "Privacy Policy | OmniInbox" };

export default function Privacy() {
  return (
    <Legal title="Privacy Policy" updated="30 September 2026" sections={[
      ["Who we are", "OmniInbox provides a shared inbox for customer messaging. For account data we are the controller; for the messages and contacts you process through the Service we act as a processor on your behalf."],
      ["Data we collect", "Account data (name, email, password hash), workspace and billing records, channel configuration (tokens and passwords are encrypted at rest), and the messages, contacts and attachments delivered to your connected channels. We also keep basic technical logs for security."],
      ["How we use it", "To provide and secure the Service, deliver and display messages, process payments, provide support and, in aggregate, improve the product. We do not sell personal data or use your customers' messages for advertising."],
      ["Sharing", "With the messaging platforms you connect (to send and receive messages), payment providers (Khalti, eSewa, Stripe) for billing, and infrastructure providers that host the Service, all under confidentiality obligations. We may disclose data when required by law."],
      ["Security", "Encryption in transit (HTTPS) and at rest for credentials, workspace isolation, role-based access, signature-verified webhooks, rate limiting and access logging."],
      ["Retention", "Data is kept while your workspace is active and deleted on request or after account closure, except records we must keep for legal or accounting reasons."],
      ["Your rights", "You can access, correct, export or delete your data. Workspace owners can request deletion of workspace data. Contact privacy@omniinbox.app."],
      ["Changes", "We will post updates here and notify workspace owners of material changes."],
    ]} />
  );
}
