"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ImagePlus, LoaderCircle, Package, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Product } from "@/lib/types";
import { UpgradeHint, useMe } from "@/components/AppShell";
import { money } from "@/components/commerce/ui";

type Draft = Partial<Product> & { id?: number; variantsText?: string };

function Editor({ draft, onClose, onSaved }: { draft: Draft; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [d, setD] = useState<Draft>({ ...draft, variantsText: (draft.variants ?? []).join(", ") });
  const [busy, setBusy] = useState(""); const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const set = (k: keyof Draft, v: unknown) => setD((x) => ({ ...x, [k]: v }));

  async function upload(f: File) {
    setBusy("img"); setError("");
    try { const r = await Api.uploadProductImage(f); setD((x) => ({ ...x, image_id: r.id, image_url: r.url })); }
    catch (err) { setError(err instanceof Error ? err.message.replace(/^file: /, "") : t("Upload failed")); } finally { setBusy(""); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy("save"); setError("");
    const variants = (d.variantsText ?? "").split(",").map((v) => v.trim()).filter(Boolean);
    try {
      await Api.saveProduct(d.id ?? null, {
        name: d.name, sku: d.sku ?? "", description: d.description ?? "", price: d.price, compare_at_price: d.compare_at_price || null,
        stock: d.stock === undefined || (d.stock as unknown) === "" ? null : d.stock, variants, image_id: d.image_id ?? null, active: d.active ?? true,
      });
      onSaved();
    } catch (err) { setError(err instanceof Error ? err.message : t("Couldn't save")); setBusy(""); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true">
      <form onSubmit={save} className="card max-h-[90vh] w-full max-w-lg space-y-3 overflow-y-auto p-5">
        <div className="flex items-center justify-between"><h2 className="font-semibold">{d.id ? t("Edit product") : t("New product")}</h2>
          <button type="button" className="btn-ghost px-2" onClick={onClose} aria-label={t("Close")}><X size={16} /></button></div>
        <div className="flex gap-3">
          <button type="button" onClick={() => file.current?.click()} className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg border-2 border-dashed border-slate-300 text-slate-400 hover:border-brand-400">
            {busy === "img" ? <LoaderCircle className="animate-spin" /> : d.image_url
              // eslint-disable-next-line @next/next/no-img-element
              ? <img src={d.image_url} alt="" className="h-full w-full object-cover" /> : <ImagePlus />}
          </button>
          <input ref={file} type="file" accept="image/jpeg,image/png" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
          <div className="flex-1 space-y-2">
            <input className="input" placeholder={t("Product name")} required maxLength={200} value={d.name ?? ""} onChange={(e) => set("name", e.target.value)} />
            <input className="input" placeholder={t("SKU / code (optional)")} maxLength={60} value={d.sku ?? ""} onChange={(e) => set("sku", e.target.value)} />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <label className="text-sm">{t("Price")}<input className="input mt-1" type="number" min={0} step="0.01" required value={d.price ?? ""} onChange={(e) => set("price", e.target.value)} /></label>
          <label className="text-sm">{t("Old price")}<input className="input mt-1" type="number" min={0} step="0.01" placeholder={t("optional")} value={d.compare_at_price ?? ""} onChange={(e) => set("compare_at_price", e.target.value)} /></label>
          <label className="text-sm">{t("Stock")}<input className="input mt-1" type="number" placeholder={t("not tracked")} value={d.stock ?? ""} onChange={(e) => set("stock", e.target.value === "" ? null : Number(e.target.value))} /></label>
        </div>
        <label className="block text-sm">{t("Sizes / colours (comma separated)")}<input className="input mt-1" placeholder="S, M, L, XL" value={d.variantsText ?? ""} onChange={(e) => set("variantsText", e.target.value)} /></label>
        <label className="block text-sm">{t("Description")}<textarea className="input mt-1 min-h-[80px]" maxLength={3000} value={d.description ?? ""} onChange={(e) => set("description", e.target.value)} placeholder={t("Material, fit, care. The AI assistant can use this to answer customers.")} /></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand-600" checked={d.active ?? true} onChange={(e) => set("active", e.target.checked)} /> {t("Available for new orders")}</label>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn-primary" disabled={!!busy}>{busy === "save" && <LoaderCircle className="animate-spin" size={15} />} {t("Save")}</button></div>
      </form>
    </div>
  );
}

export default function ProductsPage() {
  const t = useT();
  const { can } = useMe();
  const [items, setItems] = useState<Product[] | null>(null);
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [locked, setLocked] = useState(false);

  const load = () => Api.products(q).then(setItems).catch((e) => { if (e instanceof ApiError && e.status === 402) setLocked(true); });
  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  if (locked) return <div className="mx-auto max-w-2xl p-6"><UpgradeHint feature={t("Products & orders")}>{t("Keep a product catalog and take orders in chat on Starter and above.")}</UpgradeHint></div>;
  const edit = can("manage_products");

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <Link href="/orders" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={16} /> {t("Orders")}</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold">{t("Products")}</h1>
          <label className="relative ml-auto block w-full sm:w-64"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="input pl-9" placeholder={t("Search name or SKU")} value={q} onChange={(e) => setQ(e.target.value)} /></label>
          {edit && <button type="button" className="btn-primary" onClick={() => setDraft({ active: true })}><Plus size={16} /> {t("Add product")}</button>}
        </div>
        {items === null ? <LoaderCircle className="mt-6 animate-spin text-slate-400" /> : items.length === 0 ? (
          <div className="card mt-5 p-10 text-center"><Package className="mx-auto text-slate-300" size={36} />
            <p className="mt-2 font-medium">{t("No products yet")}</p><p className="text-sm text-slate-500">{t("Add what you sell with price, sizes and a photo. Picking them in an order fills the price for you.")}</p></div>
        ) : (
          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((p) => (
              <div key={p.id} className={`card overflow-hidden ${p.active ? "" : "opacity-60"}`}>
                <div className="aspect-square bg-slate-100">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {p.image_url ? <img src={p.image_url} alt="" className="h-full w-full object-cover" /> : <Package className="m-auto h-full text-slate-300" size={40} />}
                </div>
                <div className="p-3">
                  <p className="truncate font-medium">{p.name}</p>
                  <p className="text-sm"><b>{money(p.price)}</b>{p.compare_at_price && <span className="ml-1 text-xs text-slate-400 line-through">{money(p.compare_at_price)}</span>}</p>
                  <p className="text-xs text-slate-500">{p.stock === null ? t("Stock not tracked") : p.stock <= 0 ? <span className="text-red-600">{t("Out of stock")}</span> : t("{n} in stock", { n: p.stock })}{p.variants.length > 0 && ` · ${p.variants.join(", ")}`}</p>
                  {edit && (
                    <div className="mt-2 flex gap-1">
                      <button type="button" className="btn-ghost px-2" aria-label={t("Edit")} onClick={() => setDraft(p)}><Pencil size={14} /></button>
                      <button type="button" className="btn-ghost px-2 text-red-600" aria-label={t("Delete")} onClick={async () => { if (window.confirm(t("Delete {name}?", { name: p.name }))) { await Api.deleteProduct(p.id); load(); } }}><Trash2 size={14} /></button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {draft && <Editor draft={draft} onClose={() => setDraft(null)} onSaved={() => { setDraft(null); load(); }} />}
    </div>
  );
}
