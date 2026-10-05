import { ChevronDown } from "lucide-react";

export const FAQS: Array<[string, string]> = [
  ["Which platforms can I connect?",
    "WhatsApp Business, Instagram Direct (and post comments), Facebook Messenger (and Page comments), TikTok Business Messaging, Viber bots, Telegram bots, Discord bots, a chat bubble for your own website, Gmail, Outlook / Microsoft 365, Zoho Mail and any IMAP/SMTP mailbox."],
  ["How does the AI chatbot work? Will it say wrong things?",
    "You add your products, prices and policies to the knowledge base, and the AI answers only from that, in the customer's language (Nepali, Romanized Nepali or English). When it doesn't know, or the customer wants to order, pay, get a refund or complain, it hands the chat to your team. It stops in a conversation as soon as an agent replies. You can run it 24/7 or only outside business hours."],
  ["What are AI credits?",
    "One credit is one AI action: a chatbot answer, a reply suggestion, a rewrite, a summary or a set of post captions. Every plan includes monthly credits (50 on Free up to 10,000 on Business), and they reset on the 1st of each month."],
  ["Can I post to my social accounts too?",
    "Yes. From the Publish page you write one post and send it to your Facebook Page, Instagram, YouTube and TikTok, straight away or scheduled on a calendar. Publishing is included from Starter, and scheduling from Pro."],
  ["Do my customers need to install anything?",
    "No. Customers keep messaging you on the apps they already use. Your team replies from OmniInbox and the reply is delivered on the same platform."],
  ["How does the free trial work?",
    "Every new workspace gets 14 days of the Pro plan with no card required. When the trial ends you can pick a paid plan or continue on the Free plan."],
  ["How can I pay?",
    "In Nepal you can pay in rupees with Khalti or eSewa. International customers can pay in US dollars by card through Stripe. Yearly billing saves 20%."],
  ["What are the team roles?",
    "Owner (everything including billing), Admin (channels, team and settings), Supervisor (all conversations, assignment, saved replies and analytics) and Agent (replies to conversations)."],
  ["Is my data secure?",
    "Channel tokens and passwords are encrypted at rest, every workspace is isolated, webhooks are signature-verified and all traffic is served over HTTPS."],
  ["Can I change or cancel my plan?",
    "Yes. Plans are prepaid per month or year. Upgrade any time from the Billing page; if you don't renew, your workspace moves to the Free plan and your data is kept."],
];

export default function Faq() {
  return (
    <div className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
      {FAQS.map(([q, a]) => (
        <details key={q} className="group px-5 py-4 [&_summary::-webkit-details-marker]:hidden">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium text-slate-900">
            {q}
            <ChevronDown size={18} className="shrink-0 text-slate-400 transition group-open:rotate-180" />
          </summary>
          <p className="mt-3 text-sm leading-relaxed text-slate-600">{a}</p>
        </details>
      ))}
    </div>
  );
}
