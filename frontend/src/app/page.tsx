import Link from "next/link";
import {
  ArrowRight, BarChart3, Bell, Bot, CalendarClock, MessageCircleReply, Lock, MessageSquareText, Plug, Reply, ShieldCheck, StickyNote, Tags, UserCheck, Users, Wallet,
} from "lucide-react";
import InboxMockup from "@/components/marketing/InboxMockup";
import Header from "@/components/marketing/Header";
import Footer from "@/components/marketing/Footer";
import SiteChat from "@/components/marketing/SiteChat";
import PricingPlans from "@/components/marketing/Pricing";
import Faq from "@/components/marketing/Faq";
import AffiliateSection from "@/components/marketing/AffiliateSection";
import { PROVIDER_ORDER, ProviderIcon, providerUI } from "@/lib/providers";

const FEATURES = [
  { icon: MessageSquareText, title: "One inbox for every channel", text: "Chats, DMs and email threads from 9 platforms in one list, with the platform's symbol on every conversation." },
  { icon: Bot, title: "24/7 AI chatbot", text: "Answers customers in Nepali, Romanized Nepali or English from your own product info, and hands orders and complaints to your team." },
  { icon: MessageCircleReply, title: "Comment-to-DM", text: "Someone comments \"price?\" on your Facebook or Instagram post and instantly gets the details in their inbox." },
  { icon: CalendarClock, title: "Publish and schedule posts", text: "Write once and post to your Facebook Page, Instagram, YouTube and TikTok, now or on a content calendar." },
  { icon: UserCheck, title: "Assign and collaborate", text: "Assign conversations, see who's handling what, and close them when they're done. No double replies." },
  { icon: Reply, title: "AI reply suggestions", text: "One click drafts a reply from your knowledge base. Rewrite, polish or translate to Nepali before sending. Saved replies with /." },
  { icon: StickyNote, title: "Internal notes", text: "Leave context for teammates inside the conversation. Customers never see notes." },
  { icon: Tags, title: "Tags and filters", text: "Label conversations as VIP, order issue or lead, then filter by tag, channel, status or assignee." },
  { icon: BarChart3, title: "Team analytics", text: "Track message volume, first response time and replies per agent, and export to CSV." },
];

const STEPS = [
  { icon: Plug, title: "Connect your channels", text: "Paste a bot token, sign in with Microsoft, or link your Meta page. Most channels take under 5 minutes." },
  { icon: Users, title: "Invite your team", text: "Send invite links, pick each person's role and share the workload." },
  { icon: Bell, title: "Reply from one place", text: "New messages appear instantly. Replies go back on the customer's own app." },
];

const ROLES = [
  { role: "Owner", text: "Full control including billing and plan changes.", color: "bg-violet-100 text-violet-700" },
  { role: "Admin", text: "Connects channels, manages the team and workspace settings.", color: "bg-sky-100 text-sky-700" },
  { role: "Supervisor", text: "Sees every conversation, assigns work, manages saved replies and views analytics.", color: "bg-amber-100 text-amber-800" },
  { role: "Agent", text: "Replies to customers, takes or releases conversations, and leaves notes.", color: "bg-emerald-100 text-emerald-700" },
];

export default function Landing() {
  const channels = PROVIDER_ORDER.filter((p) => p !== "imap");
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <Header />
      <main className="flex-1">
      {/* Hero */}
      <section className="relative overflow-hidden bg-slate-950">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.35),transparent_60%)]" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-[1fr_1.1fr] lg:pt-24">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-slate-200">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> 14-day free trial · no card required
            </p>
            <h1 className="mt-5 text-4xl font-bold leading-[1.1] tracking-tight text-white sm:text-5xl">
              Every customer conversation.<br />
              <span className="bg-gradient-to-r from-indigo-300 to-sky-300 bg-clip-text text-transparent">One shared inbox.</span>
            </h1>
            <p className="mt-5 max-w-lg text-lg leading-relaxed text-slate-300">
              OmniInbox brings WhatsApp, Instagram, Messenger, TikTok, Telegram, Discord, Gmail, Outlook and Zoho Mail into one inbox, so your team answers every customer quickly.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/register" className="btn-primary px-5 py-3 text-base">Start free trial <ArrowRight size={18} /></Link>
              <Link href="/pricing" className="btn px-5 py-3 text-base text-white ring-1 ring-white/20 hover:bg-white/10">See pricing</Link>
            </div>
            <p className="mt-5 flex items-center gap-2 text-sm text-slate-400"><Wallet size={16} /> Pay with Khalti, eSewa or card</p>
          </div>
          <InboxMockup />
        </div>
      </section>

      {/* Channels */}
      <section id="channels" className="scroll-mt-20 border-b border-slate-100 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <p className="text-center text-sm font-semibold uppercase tracking-wider text-slate-500">Works with the apps your customers already use</p>
          <div className="mt-8 grid grid-cols-3 gap-4 sm:grid-cols-5 lg:grid-cols-9">
            {channels.map((p) => (
              <div key={p} className="flex flex-col items-center gap-2 rounded-xl p-3 transition hover:bg-slate-50">
                <ProviderIcon provider={p} size="xl" />
                <span className="text-center text-xs font-medium text-slate-700">{providerUI(p).label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="scroll-mt-20 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Everything a support team needs</h2>
            <p className="mt-4 text-lg text-slate-600">Stop switching between apps and missing messages. Work together in one place.</p>
          </div>
          <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="rounded-2xl border border-slate-200 p-6 transition hover:border-brand-200 hover:shadow-lg hover:shadow-brand-500/5">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600"><f.icon size={20} /></span>
                <h3 className="mt-4 font-semibold text-slate-900">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{f.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-slate-50">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">Live in three steps</h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <div key={s.title} className="relative rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
                <span className="absolute -top-3 left-6 rounded-full bg-brand-600 px-2.5 py-0.5 text-xs font-bold text-white">Step {i + 1}</span>
                <s.icon className="mt-2 text-brand-600" size={24} />
                <h3 className="mt-3 font-semibold text-slate-900">{s.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{s.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Roles */}
      <section id="roles" className="scroll-mt-20 bg-white">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-slate-900">The right access for every teammate</h2>
            <p className="mt-4 text-lg text-slate-600">
              Four roles keep billing with the owner, channel setup with admins and conversations with the people answering them.
              On Business, agents can be limited to their own conversations.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-slate-700">
              {["Invite links that expire after 7 days", "Change roles or remove members any time", "Every workspace fully isolated"].map((t) => (
                <li key={t} className="flex items-center gap-2"><ShieldCheck size={18} className="text-emerald-600" /> {t}</li>
              ))}
            </ul>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {ROLES.map((r) => (
              <div key={r.role} className="rounded-2xl border border-slate-200 p-5">
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${r.color}`}>{r.role}</span>
                <p className="mt-3 text-sm text-slate-600">{r.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-20 bg-slate-50">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <div className="mx-auto mb-10 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Simple pricing that grows with you</h2>
            <p className="mt-4 text-lg text-slate-600">Pay monthly or save 20% yearly. In rupees or dollars.</p>
          </div>
          <PricingPlans />
          <p className="mt-8 text-center"><Link href="/pricing" className="font-medium text-brand-600 hover:text-brand-700">Compare all features →</Link></p>
        </div>
      </section>

      {/* Affiliate program */}
      <AffiliateSection />

      {/* Security + FAQ */}
      <section className="bg-white">
        <div className="mx-auto grid max-w-6xl gap-12 px-4 py-20 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-slate-900">Questions, answered</h2>
            <p className="mt-4 text-slate-600">Can&apos;t find what you need? <Link href="/contact" className="font-medium text-brand-600">Talk to us</Link>.</p>
            <div className="mt-8 rounded-2xl bg-slate-950 p-6 text-slate-300">
              <Lock className="text-indigo-300" />
              <p className="mt-3 font-semibold text-white">Security built in</p>
              <p className="mt-2 text-sm">Encrypted credentials, signed webhooks, rate limiting, strict security headers and role-based access on every request.</p>
            </div>
          </div>
          <Faq />
        </div>
      </section>

      {/* CTA */}
      <section className="bg-gradient-to-br from-brand-600 to-indigo-800">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-4 py-16 text-center sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-white">Answer every customer from one place</h2>
          <p className="max-w-xl text-indigo-100">Start your 14-day Pro trial today. No credit card, no setup fee.</p>
          <Link href="/register" className="btn bg-white px-6 py-3 text-base text-brand-700 hover:bg-indigo-50">Create your workspace <ArrowRight size={18} /></Link>
        </div>
      </section>
    </main>
      <Footer />
      <SiteChat />
    </div>
  );
}
