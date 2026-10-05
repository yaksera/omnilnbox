"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Search } from "lucide-react";

export type SearchItem = { slug: string; title: string; category: string; summary: string; text: string };

export default function DocsSearch({ items }: { items: SearchItem[] }) {
  const [q, setQ] = useState("");
  const results = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    return items
      .map((d) => {
        const title = d.title.toLowerCase();
        const text = d.text.toLowerCase();
        if (!words.every((w) => text.includes(w))) return null;
        const score = words.reduce((s, w) => s + (title.includes(w) ? 5 : 0) + (d.summary.toLowerCase().includes(w) ? 2 : 0) + 1, 0);
        return { d, score };
      })
      .filter((r): r is { d: SearchItem; score: number } => r !== null)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
  }, [q, items]);

  return (
    <div className="relative mx-auto max-w-xl">
      <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search the help center: WhatsApp, Khalti, chatbot…"
        aria-label="Search the help center"
        className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-11 pr-4 text-base shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-200"
      />
      {q.trim() && (
        <div className="absolute left-0 right-0 top-full z-20 mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white text-left shadow-lg">
          {results.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-500">No articles match. Try other words, or see <Link href="/docs/troubleshooting" className="text-brand-700 underline">Troubleshooting</Link>.</p>
          ) : results.map(({ d }) => (
            <Link key={d.slug} href={`/docs/${d.slug}`} className="block border-b border-slate-100 px-4 py-3 last:border-0 hover:bg-slate-50">
              <p className="text-sm font-medium text-slate-900">{d.title} <span className="ml-1 text-xs font-normal text-slate-400">{d.category}</span></p>
              <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{d.summary}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
