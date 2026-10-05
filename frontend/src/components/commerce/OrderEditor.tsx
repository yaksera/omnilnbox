"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, Package, Plus, Search, Trash2 } from "lucide-react";
import { Api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Order, OrderInput, PaymentMethod, Product, ShopSettings } from "@/lib/types";
import { DISTRICTS_VALLEY, PAYMENT_METHOD, money } from "./ui";

type Line = { key: string; product_id: number | null; name: string; variant: string; quantity: number; unit_price: string; variants: string[]; image_url: string; stock: number | null };
let seq = 0;
const newKey = () => `l${++seq}`;

function ProductPicker({ onPick }: { onPick: (p: Product | null) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Product[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => Api.products(q, true).then(setItems).catch(() => setItems([])), 200);
    return () => clearTimeout(timer);
  }, [q, open]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <label className="relative block">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input className="input pl-9" placeholder={t("Add a product: search your catalog…")} value={q} onFocus={() => setOpen(true)}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }} />
      </label>
      {open && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          {items.map((p) => (
            <button key={p.id} type="button" onClick={() => { onPick(p); setOpen(false); setQ(""); }}
              className="flex w-full items-center gap-3 rounded px-2 py-1.5 text-left hover:bg-slate-50">
              <span className="h-9 w-9 shrink-0 overflow-hidden rounded bg-slate-100">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {p.image_url ? <img src={p.image_url} alt="" className="h-full w-full object-cover" /> : <Package size={16} className="m-2.5 text-slate-400" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{p.name}</span>
                <span className="text-xs text-slate-500">{money(p.price)}{p.stock !== null && ` · ${t("{n} in stock", { n: p.stock })}`}{p.variants.length > 0 && ` · ${p.variants.join(", ")}`}</span>
              </span>
            </button>
          ))}
          {items.length === 0 && <p className="px-2 py-2 text-sm text-slate-500">{q ? t("No matching products.") : t("Your catalog is empty.")}</p>}
          <button type="button" onClick={() => { onPick(null); setOpen(false); }} className="mt-1 flex w-full items-center gap-2 rounded border-t border-slate-100 px-2 py-2 text-left text-sm text-brand-700 hover:bg-slate-50">
            <Plus size={14} /> {t("Add a custom item (not in the catalog)")}
          </button>
        </div>
      )}
    </div>
  );
}

export default function OrderEditor({ initial, conversationId, shop }: { initial?: Order; conversationId?: string | null; shop: ShopSettings }) {
  const t = useT();
  const router = useRouter();
  const [lines, setLines] = useState<Line[]>(() => (initial?.items ?? []).map((i) => ({
    key: newKey(), product_id: i.product_id, name: i.name, variant: i.variant, quantity: i.quantity, unit_price: i.unit_price,
    variants: [], image_url: i.image_url ?? "", stock: null,
  })));
  const [form, setForm] = useState({
    recipient_name: initial?.recipient_name ?? "", recipient_phone: initial?.recipient_phone ?? "", address: initial?.address ?? "",
    city: initial?.city ?? "", district: initial?.district ?? "", note: initial?.note ?? "",
    payment_method: (initial?.payment_method ?? "cod") as PaymentMethod,
    delivery_charge: initial?.delivery_charge ?? "", discount: initial?.discount ?? "0",
  });
  const [chargeTouched, setChargeTouched] = useState(!!initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  // Prefill the customer from the chat (name / phone / saved address)
  useEffect(() => {
    if (initial || !conversationId) return;
    Api.conversationCustomer(conversationId).then((r) => {
      const c = r.customer;
      setForm((f) => ({
        ...f,
        recipient_name: c?.name || r.suggested?.name || f.recipient_name,
        recipient_phone: c?.phone || r.suggested?.phone || f.recipient_phone,
        address: c?.address || f.address, city: c?.city || f.city, district: c?.district || f.district,
      }));
    }).catch(() => undefined);
  }, [conversationId, initial]);

  const subtotal = useMemo(() => lines.reduce((s, l) => s + Number(l.unit_price || 0) * l.quantity, 0), [lines]);
  const autoCharge = useMemo(() => {
    const where = `${form.district} ${form.city}`.toLowerCase();
    const inside = !where.trim() || DISTRICTS_VALLEY.some((d) => where.includes(d.toLowerCase())) || where.includes("patan");
    return inside ? shop.delivery_inside_valley : shop.delivery_outside_valley;
  }, [form.district, form.city, shop]);
  const charge = chargeTouched ? form.delivery_charge : autoCharge;
  const total = Math.max(0, subtotal + Number(charge || 0) - Number(form.discount || 0));

  function add(p: Product | null) {
    setLines((ls) => [...ls, p
      ? { key: newKey(), product_id: p.id, name: p.name, variant: p.variants[0] ?? "", quantity: 1, unit_price: p.price, variants: p.variants, image_url: p.image_url, stock: p.stock }
      : { key: newKey(), product_id: null, name: "", variant: "", quantity: 1, unit_price: "", variants: [], image_url: "", stock: null }]);
  }
  const upd = (key: string, patch: Partial<Line>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!lines.length) { setError(t("Add at least one item.")); return; }
    setBusy(true); setError("");
    const body: OrderInput = {
      ...form, delivery_charge: String(charge || 0), discount: String(form.discount || 0),
      items: lines.map((l) => ({ product_id: l.product_id, name: l.name, variant: l.variant, quantity: l.quantity, unit_price: l.unit_price || null })),
      ...(initial ? {} : { conversation_id: conversationId ?? null }),
    };
    try {
      const o = await Api.saveOrder(initial?.id ?? null, body);
      router.push(`/orders/${o.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn't save the order"));
      setBusy(false);
    }
  }

  const locked = !!initial && ["shipped", "delivered", "cancelled", "returned"].includes(initial.status);

  return (
    <form onSubmit={save} className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-5">
        <section className="card p-4">
          <h2 className="font-semibold">{t("Items")}</h2>
          {!locked && <div className="mt-3"><ProductPicker onPick={add} /></div>}
          <div className="mt-3 divide-y divide-slate-100">
            {lines.length === 0 && <p className="py-6 text-center text-sm text-slate-500">{t("No items yet. Search your catalog above or add a custom item.")}</p>}
            {lines.map((l) => (
              <div key={l.key} className="flex flex-wrap items-center gap-2 py-3">
                <span className="h-10 w-10 shrink-0 overflow-hidden rounded bg-slate-100">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {l.image_url ? <img src={l.image_url} alt="" className="h-full w-full object-cover" /> : <Package size={16} className="m-3 text-slate-400" />}
                </span>
                <input className="input min-w-[140px] flex-1" placeholder={t("Item name")} value={l.name} disabled={locked || !!l.product_id} required
                  onChange={(e) => upd(l.key, { name: e.target.value })} />
                {l.variants.length > 0 ? (
                  <select className="input w-24" value={l.variant} disabled={locked} onChange={(e) => upd(l.key, { variant: e.target.value })} aria-label={t("Option")}>
                    {l.variants.map((v) => <option key={v}>{v}</option>)}
                  </select>
                ) : (
                  <input className="input w-24" placeholder={t("Size/colour")} value={l.variant} disabled={locked} onChange={(e) => upd(l.key, { variant: e.target.value })} />
                )}
                <input className="input w-16 text-center" type="number" min={1} value={l.quantity} disabled={locked} aria-label={t("Quantity")}
                  onChange={(e) => upd(l.key, { quantity: Math.max(1, Number(e.target.value) || 1) })} />
                <span className="text-slate-400">×</span>
                <input className="input w-24 text-right" type="number" min={0} step="0.01" placeholder={t("Price")} value={l.unit_price} disabled={locked} required aria-label={t("Unit price")}
                  onChange={(e) => upd(l.key, { unit_price: e.target.value })} />
                <span className="w-24 text-right text-sm font-medium">{money(Number(l.unit_price || 0) * l.quantity)}</span>
                {!locked && <button type="button" className="btn-ghost px-2 text-red-600" aria-label={t("Remove item")} onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))}><Trash2 size={15} /></button>}
                {l.stock !== null && l.quantity > l.stock && <p className="w-full pl-12 text-xs text-amber-700">{t("Only {n} in stock.", { n: l.stock })}</p>}
              </div>
            ))}
          </div>
        </section>

        <section className="card p-4">
          <h2 className="font-semibold">{t("Deliver to")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm">{t("Name")}<input className="input mt-1" value={form.recipient_name} maxLength={200} onChange={(e) => set("recipient_name", e.target.value)} /></label>
            <label className="text-sm">{t("Phone")}<input className="input mt-1" inputMode="tel" placeholder="98XXXXXXXX" value={form.recipient_phone} maxLength={30} onChange={(e) => set("recipient_phone", e.target.value)} /></label>
            <label className="text-sm sm:col-span-2">{t("Address")}<input className="input mt-1" placeholder={t("Tole, street, landmark")} value={form.address} maxLength={300} onChange={(e) => set("address", e.target.value)} /></label>
            <label className="text-sm">{t("City / area")}<input className="input mt-1" placeholder={t("e.g. Baneshwor, Pokhara")} value={form.city} maxLength={100} onChange={(e) => set("city", e.target.value)} /></label>
            <label className="text-sm">{t("District")}<input className="input mt-1" list="np-districts" placeholder={t("e.g. Kathmandu, Kaski")} value={form.district} maxLength={100} onChange={(e) => set("district", e.target.value)} /></label>
          </div>
          <datalist id="np-districts">
            {["Kathmandu", "Lalitpur", "Bhaktapur", "Kaski", "Chitwan", "Rupandehi", "Morang", "Sunsari", "Jhapa", "Dhanusha", "Parsa", "Banke", "Kailali", "Makwanpur", "Kavrepalanchok", "Nawalparasi", "Tanahun", "Syangja", "Palpa", "Ilam", "Surkhet", "Dang", "Bara", "Saptari", "Siraha", "Mahottari", "Sarlahi", "Dhading", "Nuwakot", "Sindhupalchok"].map((d) => <option key={d} value={d} />)}
          </datalist>
          <label className="mt-3 block text-sm">{t("Note (for your team / the courier)")}
            <textarea className="input mt-1 min-h-[60px]" maxLength={2000} value={form.note} onChange={(e) => set("note", e.target.value)} placeholder={t("e.g. Call before delivery, gift wrap")} />
          </label>
        </section>
      </div>

      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <section className="card space-y-3 p-4">
          <h2 className="font-semibold">{t("Payment")}</h2>
          <select className="input" value={form.payment_method} onChange={(e) => set("payment_method", e.target.value)} aria-label={t("Payment method")}>
            {(Object.keys(PAYMENT_METHOD) as PaymentMethod[]).map((m) => <option key={m} value={m}>{t(PAYMENT_METHOD[m])}</option>)}
          </select>
          {(form.payment_method === "khalti" || form.payment_method === "esewa") && shop.gateways.length === 0 && (
            <p className="rounded bg-amber-50 p-2 text-xs text-amber-800">{t("Connect Khalti or eSewa in Settings → Shop to send payment links.")}</p>
          )}
          <dl className="space-y-2 border-t border-slate-100 pt-3 text-sm">
            <div className="flex justify-between"><dt className="text-slate-500">{t("Subtotal")}</dt><dd>{money(subtotal)}</dd></div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-500">{t("Delivery")} {!chargeTouched && <span className="text-[11px]">{t("(auto)")}</span>}</dt>
              <dd><input className="input w-24 py-1 text-right" type="number" min={0} value={charge} aria-label={t("Delivery charge")}
                onChange={(e) => { setChargeTouched(true); set("delivery_charge", e.target.value); }} /></dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-500">{t("Discount")}</dt>
              <dd><input className="input w-24 py-1 text-right" type="number" min={0} value={form.discount} aria-label={t("Discount")} onChange={(e) => set("discount", e.target.value)} /></dd>
            </div>
            <div className="flex justify-between border-t border-slate-100 pt-2 text-base font-semibold"><dt>{t("Total")}</dt><dd>{money(total)}</dd></div>
          </dl>
        </section>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={16} />} {initial ? t("Save changes") : t("Create order")}</button>
        {conversationId && !initial && <p className="text-center text-xs text-slate-500">{t("Linked to the chat. After saving you can send the order summary and payment link to the customer.")}</p>}
      </aside>
    </form>
  );
}
