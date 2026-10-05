import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Bot, Code2, LifeBuoy, Megaphone, MessagesSquare, BarChart3, Settings, ShoppingBag } from "lucide-react";
import { CATEGORIES, DOCS, byCategory, docText } from "@/content/docs";
import DocsSearch from "@/components/docs/DocsSearch";

export const metadata: Metadata = {
  title: "Help center | OmniInbox",
  description: "Step-by-step guides with screenshots: connect WhatsApp, Instagram, Messenger and Viber, set up the AI chatbot, take orders, Khalti/eSewa payments and couriers.",
};

const ICONS = {
  "Getting started": BookOpen, Channels: MessagesSquare, "AI & automation": Bot, Selling: ShoppingBag,
  Marketing: Megaphone, Reports: BarChart3, Account: Settings, Developers: Code2, Help: LifeBuoy,
} as const;

const POPULAR = ["getting-started", "whatsapp", "messenger", "ai-assistant", "orders", "payments"];

export default function DocsIndex() {
  const items = DOCS.map((d) => ({ slug: d.slug, title: d.title, category: d.category, summary: d.summary, text: docText(d) }));
  return (
    <>
      <section className="border-b border-slate-200 bg-gradient-to-b from-brand-50 to-white">
        <div className="mx-auto max-w-4xl px-4 pb-12 pt-14 text-center sm:px-6">
          <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">Help center</p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">How can we help?</h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-600">Step-by-step setup guides with screenshots for every channel and feature.</p>
          <div className="mt-8"><DocsSearch items={items} /></div>
          <div className="mt-5 flex flex-wrap justify-center gap-2 text-sm">
            <span className="text-slate-500">Popular:</span>
            {POPULAR.map((s) => {
              const d = DOCS.find((x) => x.slug === s);
              return d && <Link key={s} href={`/docs/${s}`} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-700 hover:border-brand-300 hover:text-brand-700">{d.title.replace(/^Connect /, "")}</Link>;
            })}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {CATEGORIES.map((c) => {
            const Icon = ICONS[c.name];
            const docs = byCategory(c.name);
            return (
              <div key={c.name} className="flex flex-col rounded-2xl border border-slate-200 p-5">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700"><Icon size={20} /></span>
                  <div>
                    <h2 className="font-semibold text-slate-900">{c.name}</h2>
                    <p className="text-xs text-slate-500">{docs.length} {docs.length === 1 ? "article" : "articles"}</p>
                  </div>
                </div>
                <p className="mt-3 text-sm text-slate-600">{c.blurb}</p>
                <ul className="mt-4 space-y-1.5">
                  {docs.map((d) => (
                    <li key={d.slug}>
                      <Link href={`/docs/${d.slug}`} className="group flex items-center gap-1.5 text-sm text-slate-700 hover:text-brand-700">
                        <ArrowRight size={14} className="shrink-0 text-slate-300 group-hover:text-brand-600" />{d.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-4 rounded-2xl bg-slate-900 px-6 py-8 text-center sm:flex-row sm:text-left">
          <div>
            <p className="text-lg font-semibold text-white">Can&apos;t find what you need?</p>
            <p className="text-sm text-slate-300">Send us a message and we&apos;ll help you set it up.</p>
          </div>
          <Link href="/contact" className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100">Contact support</Link>
        </div>
      </section>
    </>
  );
}
