import Link from "next/link";
import { AlertTriangle, Lightbulb } from "lucide-react";
import type { Block } from "@/content/docs";

/** Inline markup: **bold**, *italic*, `code`, [text](href). */
export function Inline({ text }: { text: string }) {
  const out: React.ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|\*([^*\s][^*]*?)\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined) out.push(<strong key={k++} className="font-semibold text-slate-900"><Inline text={m[1]} /></strong>);
    else if (m[2] !== undefined) out.push(<code key={k++} className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.85em] text-slate-800">{m[2]}</code>);
    else if (m[3] !== undefined) {
      const href = m[4];
      out.push(href.startsWith("/")
        ? <Link key={k++} href={href} className="font-medium text-brand-700 underline-offset-2 hover:underline">{m[3]}</Link>
        : <a key={k++} href={href} target="_blank" rel="noopener noreferrer" className="font-medium text-brand-700 underline-offset-2 hover:underline">{m[3]}</a>);
    } else if (m[5] !== undefined) out.push(<em key={k++}>{m[5]}</em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}

export function slugify(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default function DocBody({ body }: { body: Block[] }) {
  return (
    <div className="space-y-5 text-[15px] leading-7 text-slate-700">
      {body.map((b, i) => {
        if ("h" in b) return <h2 key={i} id={slugify(b.h)} className="scroll-mt-24 pt-4 text-xl font-semibold text-slate-900">{b.h}</h2>;
        if ("p" in b) return <p key={i}><Inline text={b.p} /></p>;
        if ("steps" in b) return (
          <ol key={i} className="space-y-3">
            {b.steps.map((s, j) => (
              <li key={j} className="flex gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white">{j + 1}</span>
                <span className="min-w-0"><Inline text={s} /></span>
              </li>
            ))}
          </ol>
        );
        if ("list" in b) return (
          <ul key={i} className="list-disc space-y-1.5 pl-5 marker:text-slate-400">
            {b.list.map((s, j) => <li key={j}><Inline text={s} /></li>)}
          </ul>
        );
        if ("img" in b) return (
          <figure key={i} className={b.narrow ? "max-w-xl" : ""}>
            <a href={`/docs-img/${b.img}.webp`} target="_blank" rel="noopener noreferrer" title="Open full size">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/docs-img/${b.img}.webp`} alt={b.alt} loading="lazy" className="w-full rounded-xl border border-slate-200 shadow-sm" />
            </a>
            <figcaption className="mt-2 text-center text-xs text-slate-500">{b.caption || b.alt}</figcaption>
          </figure>
        );
        if ("tip" in b) return (
          <div key={i} className="flex gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
            <Lightbulb size={18} className="mt-0.5 shrink-0" /><p><Inline text={b.tip} /></p>
          </div>
        );
        if ("warn" in b) return (
          <div key={i} className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" /><p><Inline text={b.warn} /></p>
          </div>
        );
        if ("code" in b) return (
          <pre key={i} className="overflow-x-auto rounded-xl bg-slate-900 p-4 text-[13px] leading-6 text-slate-100"><code>{b.code}</code></pre>
        );
        if ("table" in b) return (
          <div key={i} className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-900">
                <tr>{b.table.head.map((h) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {b.table.rows.map((r, j) => (
                  <tr key={j} className="align-top">{r.map((c, n) => <td key={n} className="px-3 py-2"><Inline text={c} /></td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        return null;
      })}
    </div>
  );
}
