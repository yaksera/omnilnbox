import Link from "next/link";
import Logo from "@/components/Logo";
import { PROVIDER_ORDER, ProviderIcon } from "@/lib/providers";

const COLS = [
  { title: "Product", links: [["Features", "/#features"], ["Channels", "/#channels"], ["Pricing", "/pricing"], ["Help center", "/docs"], ["Start free trial", "/register"]] },
  { title: "Company", links: [["Affiliate program", "/affiliates"], ["Contact sales", "/contact"], ["Log in", "/login"]] },
  { title: "Legal", links: [["Terms of Service", "/terms"], ["Privacy Policy", "/privacy"]] },
];

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-slate-50">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-5">
        <div className="md:col-span-2">
          <Logo />
          <p className="mt-3 max-w-xs text-sm text-slate-600">
            One inbox for WhatsApp, Instagram, Messenger, TikTok, Telegram, Discord and email. Built in Kathmandu for teams everywhere.
          </p>
          <div className="mt-5 flex flex-wrap gap-1.5">
            {PROVIDER_ORDER.filter((p) => p !== "imap").map((p) => <ProviderIcon key={p} provider={p} size="sm" />)}
          </div>
        </div>
        {COLS.map((c) => (
          <div key={c.title}>
            <p className="text-sm font-semibold text-slate-900">{c.title}</p>
            <ul className="mt-3 space-y-2">
              {c.links.map(([label, href]) => (
                <li key={href}><Link href={href} className="text-sm text-slate-600 hover:text-slate-900">{label}</Link></li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-200">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} OmniInbox. All rights reserved.</p>
          <p>Payments by Khalti, eSewa and Stripe · Platform names and logos belong to their owners.</p>
        </div>
      </div>
    </footer>
  );
}
