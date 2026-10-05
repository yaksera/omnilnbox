import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, ChevronRight, Clock } from "lucide-react";
import { CATEGORIES, DOCS, byCategory, getDoc } from "@/content/docs";
import DocBody, { slugify } from "@/components/docs/DocBody";

export const dynamicParams = false;

export function generateStaticParams() {
  return DOCS.map((d) => ({ slug: d.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const doc = getDoc(slug);
  if (!doc) return {};
  return { title: `${doc.title} | OmniInbox Help`, description: doc.summary };
}

export default async function DocPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = getDoc(slug);
  if (!doc) notFound();
  const i = DOCS.indexOf(doc);
  const prev = DOCS[i - 1];
  const next = DOCS[i + 1];
  const headings = doc.body.flatMap((b) => ("h" in b ? [b.h] : []));

  return (
    <div className="mx-auto flex max-w-7xl gap-10 px-4 py-10 sm:px-6">
      <aside className="hidden w-60 shrink-0 lg:block">
        <nav className="sticky top-24 max-h-[calc(100vh-7rem)] space-y-5 overflow-y-auto pb-10 pr-2 text-sm" aria-label="Help articles">
          <Link href="/docs" className="flex items-center gap-1.5 font-medium text-slate-500 hover:text-slate-900"><ArrowLeft size={14} /> All help topics</Link>
          {CATEGORIES.map((c) => (
            <div key={c.name}>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">{c.name}</p>
              <ul className="space-y-0.5">
                {byCategory(c.name).map((d) => (
                  <li key={d.slug}>
                    <Link href={`/docs/${d.slug}`} aria-current={d.slug === doc.slug ? "page" : undefined}
                      className={`block rounded-md px-2 py-1 ${d.slug === doc.slug ? "bg-brand-50 font-medium text-brand-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
                      {d.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      <article className="min-w-0 max-w-3xl flex-1">
        <nav className="flex flex-wrap items-center gap-1 text-sm text-slate-500" aria-label="Breadcrumb">
          <Link href="/docs" className="hover:text-slate-900">Help center</Link>
          <ChevronRight size={14} />
          <span>{doc.category}</span>
        </nav>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{doc.title}</h1>
        <p className="mt-3 text-lg text-slate-600">{doc.summary}</p>
        {doc.minutes && <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-400"><Clock size={14} /> {doc.minutes} min read</p>}

        {headings.length >= 3 && (
          <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
            <p className="font-semibold text-slate-900">On this page</p>
            <ul className="mt-2 grid gap-1 sm:grid-cols-2">
              {headings.map((h) => <li key={h}><a href={`#${slugify(h)}`} className="text-brand-700 hover:underline">{h}</a></li>)}
            </ul>
          </div>
        )}

        <div className="mt-8"><DocBody body={doc.body} /></div>

        <div className="mt-14 grid gap-3 border-t border-slate-200 pt-6 sm:grid-cols-2">
          {prev ? (
            <Link href={`/docs/${prev.slug}`} className="rounded-xl border border-slate-200 p-4 hover:border-brand-300">
              <p className="flex items-center gap-1 text-xs text-slate-500"><ArrowLeft size={12} /> Previous</p>
              <p className="mt-1 font-medium text-slate-900">{prev.title}</p>
            </Link>
          ) : <span />}
          {next && (
            <Link href={`/docs/${next.slug}`} className="rounded-xl border border-slate-200 p-4 text-right hover:border-brand-300">
              <p className="flex items-center justify-end gap-1 text-xs text-slate-500">Next <ArrowRight size={12} /></p>
              <p className="mt-1 font-medium text-slate-900">{next.title}</p>
            </Link>
          )}
        </div>
        <p className="mt-8 text-sm text-slate-500">Still need help? <Link href="/contact" className="font-medium text-brand-700 hover:underline">Contact support</Link> or read <Link href="/docs/troubleshooting" className="font-medium text-brand-700 hover:underline">Troubleshooting</Link>.</p>
      </article>
    </div>
  );
}
