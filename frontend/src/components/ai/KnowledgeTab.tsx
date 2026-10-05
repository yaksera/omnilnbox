"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import {
  BookOpen, ChevronDown, CircleAlert, FileText, FileUp, Globe, LoaderCircle, PenLine, Pencil, Plus, RefreshCw, Search, Sparkles, Trash2, X,
} from "lucide-react";
import { Api } from "@/lib/api";
import type { KnowledgeItem, KnowledgeMatch, KnowledgeSource } from "@/lib/types";
import { useT } from "@/lib/i18n";

const EXAMPLES = [
  { title: "Delivery charges", content: "Inside Kathmandu Valley: Rs 100, 1-2 days. Outside the Valley: Rs 150, 3-5 days. Free delivery on orders over Rs 5,000." },
  { title: "Payment options", content: "Cash on delivery, Khalti, eSewa or bank transfer (Nabil Bank). We send a payment link after confirming the order." },
  { title: "Admission process", content: "1. Fill the online form. 2. Entrance exam. 3. Interview. Bring your +2 transcript, character certificate and 4 photos." },
];
const ACCEPT = ".pdf,.docx,.txt,.md,.csv";
type Editing = { id: number | null; title: string; content: string };

function EntryCard({ k, canEdit, highlight, onEdit, onDelete }: {
  k: KnowledgeItem; canEdit: boolean; highlight: boolean; onEdit: () => void; onDelete: () => void;
}) {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (highlight) ref.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [highlight]);
  return (
    <div ref={ref} className={clsx("card group p-4", highlight && "ring-2 ring-brand-500")}>
      <div className="flex items-start gap-2">
        <p className="flex-1 font-medium">{k.title}</p>
        {canEdit && (
          <span className="flex gap-1 opacity-60 group-hover:opacity-100">
            <button type="button" className="btn-ghost px-1.5" aria-label={t("Edit")} onClick={onEdit}><Pencil size={14} /></button>
            <button type="button" className="btn-ghost px-1.5 text-red-600" aria-label={t("Delete")} onClick={onDelete}><Trash2 size={14} /></button>
          </span>
        )}
      </div>
      <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-sm text-slate-600">{k.content}</p>
    </div>
  );
}

/** "What would the AI find?": runs the same search the bot uses, for free. */
function SearchTester() {
  const t = useT();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<KnowledgeMatch[] | null>(null);
  const [busy, setBusy] = useState(false);
  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try { setRes(await Api.searchKnowledge(q.trim())); } catch { setRes([]); } finally { setBusy(false); }
  }
  return (
    <div className="card p-4">
      <p className="flex items-center gap-2 font-medium"><Sparkles size={16} className="text-brand-600" /> {t("What would the AI find?")}</p>
      <p className="mt-0.5 text-sm text-slate-500">{t("Type a customer question in English, नेपाली or Romanized Nepali to see which entries the AI would read. Free, no credits used.")}</p>
      <form onSubmit={run} className="mt-3 flex gap-2">
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("e.g. BBA ko fee kati ho?")} />
        <button className="btn-secondary shrink-0" disabled={busy || !q.trim()}>{busy ? <LoaderCircle className="animate-spin" size={16} /> : <Search size={16} />} {t("Search")}</button>
      </form>
      {res && (
        res.length === 0 ? <p className="mt-3 text-sm text-slate-500">{t("Nothing found. Add an entry that answers this question.")}</p> : (
          <ol className="mt-3 space-y-2">
            {res.map((r, i) => (
              <li key={`${r.kind}-${r.id}`} className={clsx("rounded-lg border p-3 text-sm", i === 0 ? "border-brand-200 bg-brand-50/40" : "border-slate-200")}>
                <div className="flex items-center gap-2">
                  <span className="flex-1 font-medium">{i + 1}. {r.title}</span>
                  <span className="text-xs text-slate-400">{r.match === "meaning" ? t("matched by meaning") : t("matched by words")}</span>
                  <span className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100"><span className="block h-full bg-brand-500" style={{ width: `${Math.round(Math.min(1, r.score) * 100)}%` }} /></span>
                </div>
                {r.source && <p className="text-xs text-slate-500">{t("From: {source}", { source: r.source })}</p>}
                <p className="mt-1 line-clamp-2 text-slate-600">{r.content}</p>
              </li>
            ))}
          </ol>
        )
      )}
    </div>
  );
}

export default function KnowledgeTab({ canEdit, onCount }: { canEdit: boolean; onCount: (n: number) => void }) {
  const t = useT();
  const [items, setItems] = useState<KnowledgeItem[] | null>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [open, setOpen] = useState<string>("");  // expanded group: "manual" or source id
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [upload, setUpload] = useState<{ name: string; pct: number } | null>(null);
  const [url, setUrl] = useState("");
  const [crawl, setCrawl] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [highlight, setHighlight] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const [k, s] = await Promise.all([Api.knowledge(), Api.knowledgeSources()]);
    setItems(k); setSources(s);
  }, []);
  const count = items?.length;
  useEffect(() => {
    if (count !== undefined) onCount(count);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- report only when the count changes (onCount is a new function every render)
  }, [count]);
  useEffect(() => {
    load().catch(() => setItems([]));
    // /automations?k=<entry id>#knowledge (from "Based on" in a conversation) opens and highlights that entry
    const k = Number(new URLSearchParams(window.location.search).get("k"));
    if (k) setHighlight(k);
  }, [load]);
  useEffect(() => {
    if (highlight && items) {
      const it = items.find((i) => i.id === highlight);
      if (it) setOpen(it.source ? String(it.source.id) : "manual");
    }
  }, [highlight, items]);
  // keep refreshing while documents / websites are being read
  const processing = sources.some((s) => s.status === "processing");
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => { load().catch(() => undefined); }, 2500);
    return () => clearInterval(timer);
  }, [processing, load]);

  const groups = useMemo(() => {
    const byId = new Map<string, KnowledgeItem[]>();
    for (const k of items ?? []) {
      if (q && !`${k.title} ${k.content}`.toLowerCase().includes(q.toLowerCase())) continue;
      const key = k.source ? String(k.source.id) : "manual";
      byId.set(key, [...(byId.get(key) ?? []), k]);
    }
    return byId;
  }, [items, q]);

  async function uploadFiles(files: FileList | File[]) {
    setError("");
    for (const f of Array.from(files)) {
      setUpload({ name: f.name, pct: 0 });
      try { await Api.uploadKnowledge(f, (pct) => setUpload({ name: f.name, pct })); }
      catch (err) { setError(err instanceof Error ? err.message : t("Upload failed")); }
    }
    setUpload(null);
    load().catch(() => undefined);
  }

  async function importSite(e: React.FormEvent) {
    e.preventDefault();
    setBusy("url"); setError("");
    try {
      await Api.importWebsite(url.trim().startsWith("http") ? url.trim() : `https://${url.trim()}`, crawl);
      setUrl(""); await load();
    } catch (err) { setError(err instanceof Error ? err.message : t("Couldn't import")); } finally { setBusy(""); }
  }

  async function save() {
    if (!editing) return;
    setBusy("save"); setError("");
    try {
      await Api.saveKnowledge(editing.id, { title: editing.title.trim(), content: editing.content.trim() });
      setEditing(null); await load();
    } catch (err) { setError(err instanceof Error ? err.message : t("Couldn't save")); } finally { setBusy(""); }
  }

  async function removeItem(k: KnowledgeItem) {
    if (!window.confirm(t("Delete “{title}”?", { title: k.title }))) return;
    await Api.deleteKnowledge(k.id); load().catch(() => undefined);
  }

  async function removeSource(s: KnowledgeSource) {
    if (!window.confirm(t("Delete “{name}” and its {n} entries?", { name: s.name, n: s.entries }))) return;
    await Api.deleteSource(s.id); load().catch(() => undefined);
  }

  if (!items) return <LoaderCircle className="animate-spin text-slate-400" />;
  const manual = groups.get("manual") ?? [];
  const totalManual = items.filter((k) => !k.source).length;

  const entries = (list: KnowledgeItem[]) => (
    <div className="grid gap-3 md:grid-cols-2">
      {list.map((k) => (
        <EntryCard key={k.id} k={k} canEdit={canEdit} highlight={highlight === k.id}
          onEdit={() => setEditing({ id: k.id, title: k.title, content: k.content })} onDelete={() => removeItem(k)} />
      ))}
    </div>
  );

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600">
        {t("Teach the AI about your organisation: upload your prospectus, fee structure, checklists or brochures, import your website, or write answers yourself. The AI answers only from this (plus your saved replies).")}
      </p>

      {canEdit && (
        <div className="grid gap-3 lg:grid-cols-3">
          <div onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files); }}
            className={clsx("card flex flex-col p-4 transition", dragging && "border-brand-500 bg-brand-50")}>
            <p className="flex items-center gap-2 font-medium"><FileUp size={18} className="text-brand-600" /> {t("Upload a document")}</p>
            <p className="mt-1 flex-1 text-sm text-slate-500">{t("PDF, Word (.docx) or text, up to 10 MB. Drop files here.")}</p>
            <input ref={fileRef} type="file" accept={ACCEPT} multiple className="hidden"
              onChange={(e) => { if (e.target.files?.length) uploadFiles(e.target.files); e.target.value = ""; }} />
            {upload ? (
              <div className="mt-3 text-sm">
                <p className="truncate text-slate-600">{t("Uploading {name}…", { name: upload.name })}</p>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-brand-600" style={{ width: `${upload.pct}%` }} /></div>
              </div>
            ) : (
              <button type="button" className="btn-primary mt-3" onClick={() => fileRef.current?.click()}><FileUp size={16} /> {t("Choose file")}</button>
            )}
          </div>
          <form onSubmit={importSite} className="card flex flex-col p-4">
            <p className="flex items-center gap-2 font-medium"><Globe size={18} className="text-brand-600" /> {t("Import your website")}</p>
            <input className="input mt-2" placeholder="https://yourcollege.edu.np" value={url} onChange={(e) => setUrl(e.target.value)} />
            <label className="mt-2 flex flex-1 items-start gap-2 text-sm text-slate-600">
              <input type="checkbox" className="mt-0.5 accent-brand-600" checked={crawl} onChange={(e) => setCrawl(e.target.checked)} />
              {t("Also read linked pages (About, Courses, Fees, FAQ…), up to 15 pages")}
            </label>
            <button className="btn-secondary mt-3" disabled={busy === "url" || url.trim().length < 4}>
              {busy === "url" ? <LoaderCircle className="animate-spin" size={16} /> : <Globe size={16} />} {t("Import")}
            </button>
          </form>
          <div className="card flex flex-col p-4">
            <p className="flex items-center gap-2 font-medium"><PenLine size={18} className="text-brand-600" /> {t("Write an answer")}</p>
            <p className="mt-1 flex-1 text-sm text-slate-500">{t("For facts that aren't written anywhere yet, or to correct something.")}</p>
            <button type="button" className="btn-secondary mt-3" onClick={() => setEditing({ id: null, title: "", content: "" })}><Plus size={16} /> {t("Add entry")}</button>
          </div>
        </div>
      )}

      {error && <p className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"><CircleAlert size={16} /> {t(error)}</p>}

      {editing && (
        <div className="card space-y-3 border-brand-300 p-4">
          <input className="input" placeholder={t("Title, e.g. BBA fee structure")} maxLength={200} value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
          <textarea className="input min-h-[140px]" maxLength={4000} placeholder={t("Write it the way you'd explain it to a new staff member: prices, dates, requirements, steps…")}
            value={editing.content} onChange={(e) => setEditing({ ...editing, content: e.target.value })} />
          <div className="flex gap-2">
            <button type="button" className="btn-primary" onClick={save} disabled={busy === "save" || !editing.title.trim() || !editing.content.trim()}>{busy === "save" && <LoaderCircle className="animate-spin" size={16} />} {t("Save")}</button>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}><X size={16} /> {t("Cancel")}</button>
            <span className="ml-auto self-center text-xs text-slate-400">{editing.content.length}/4000</span>
          </div>
        </div>
      )}

      {items.length > 0 && <SearchTester />}

      {items.length === 0 && sources.length === 0 && !editing ? (
        <div className="card p-6 text-center">
          <BookOpen className="mx-auto text-slate-300" size={32} />
          <p className="mt-2 font-medium">{t("Your knowledge base is empty")}</p>
          <p className="text-sm text-slate-500">{t("Upload a document or import your website above, or start from an example:")}</p>
          {canEdit && (
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((ex) => <button key={ex.title} type="button" className="btn-secondary text-xs" onClick={() => setEditing({ id: null, ...ex })}><Plus size={14} /> {t(ex.title)}</button>)}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {items.length > 6 && (
            <label className="relative block max-w-sm">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input className="input pl-9" placeholder={t("Filter entries")} value={q} onChange={(e) => setQ(e.target.value)} />
            </label>
          )}
          {sources.map((s) => {
            const list = groups.get(String(s.id)) ?? [];
            const isOpen = open === String(s.id);
            return (
              <div key={s.id} className="card overflow-hidden">
                <div className="flex flex-wrap items-center gap-3 p-4">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
                    {s.kind === "website" ? <Globe size={18} /> : <FileText size={18} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{s.name}</p>
                    <p className="text-xs text-slate-500">
                      {s.status === "processing" && <span className="inline-flex items-center gap-1 text-brand-700"><LoaderCircle size={12} className="animate-spin" /> {s.kind === "website" ? t("Reading the website…") : t("Reading the document…")}</span>}
                      {s.status === "ready" && <>{t(s.entries === 1 ? "1 entry" : "{n} entries", { n: s.entries })}{s.pages ? ` · ${t(s.kind === "website" ? (s.pages === 1 ? "1 page read" : "{n} pages read") : (s.pages === 1 ? "1 page" : "{n} pages"), { n: s.pages })}` : ""}{s.url ? ` · ${s.url}` : ""}</>}
                      {s.status === "failed" && <span className="text-red-600">{t(s.error || "Import failed")}</span>}
                    </p>
                  </div>
                  {s.status === "ready" && s.entries > 0 && (
                    <button type="button" className="btn-ghost text-sm" onClick={() => setOpen(isOpen ? "" : String(s.id))}>
                      {t("Review entries")} <ChevronDown size={15} className={clsx("transition", isOpen && "rotate-180")} />
                    </button>
                  )}
                  {canEdit && s.kind === "website" && s.status !== "processing" && (
                    <button type="button" className="btn-ghost px-2" title={t("Import again to pick up changes on the site")}
                      onClick={async () => { await Api.resyncSource(s.id).catch(() => undefined); load().catch(() => undefined); }}><RefreshCw size={15} /></button>
                  )}
                  {canEdit && <button type="button" className="btn-ghost px-2 text-red-600" aria-label={t("Delete")} onClick={() => removeSource(s)}><Trash2 size={15} /></button>}
                </div>
                {isOpen && <div className="border-t border-slate-100 bg-slate-50/60 p-4">{list.length ? entries(list) : <p className="text-sm text-slate-500">{t("No entries match.")}</p>}</div>}
              </div>
            );
          })}
          {totalManual > 0 && (
            <div className="card overflow-hidden">
              <button type="button" className="flex w-full items-center gap-3 p-4 text-left" onClick={() => setOpen(open === "manual" ? "" : "manual")}>
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 text-slate-600"><PenLine size={18} /></span>
                <span className="min-w-0 flex-1"><span className="block font-medium">{t("Written by your team")}</span>
                  <span className="text-xs text-slate-500">{t(totalManual === 1 ? "1 entry" : "{n} entries", { n: totalManual })}</span></span>
                <ChevronDown size={15} className={clsx("text-slate-500 transition", open === "manual" && "rotate-180")} />
              </button>
              {open === "manual" && <div className="border-t border-slate-100 bg-slate-50/60 p-4">{manual.length ? entries(manual) : <p className="text-sm text-slate-500">{t("No entries match.")}</p>}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
