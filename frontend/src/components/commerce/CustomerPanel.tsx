"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, LoaderCircle, Pencil, Plus, ShoppingBag } from "lucide-react";
import { Api } from "@/lib/api";
import type { Customer, OrderSummary } from "@/lib/types";
import { PaymentBadge, StatusBadge, money } from "./ui";
import { useT } from "@/lib/i18n";

const FIELDS = [["name", "Name"], ["phone", "Phone"], ["address", "Address"], ["city", "City / area"], ["district", "District"]] as const;

export default function CustomerPanel({ conversationId }: { conversationId: string }) {
  const t = useT();
  const [data, setData] = useState<{ customer: Customer | null; orders: OrderSummary[]; suggested: { name: string; phone: string } | null } | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Partial<Customer>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setData(null); setEditing(false);
    Api.conversationCustomer(conversationId).then((d) => {
      setData(d);
      setForm(d.customer ?? { name: d.suggested?.name ?? "", phone: d.suggested?.phone ?? "" });
    }).catch(() => setData({ customer: null, orders: [], suggested: null }));
  }, [conversationId]);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try {
      const r = await Api.saveConversationCustomer(conversationId, { name: form.name, phone: form.phone, address: form.address, city: form.city, district: form.district });
      setData({ ...r, suggested: null }); setEditing(false);
    } finally { setBusy(false); }
  }

  if (!data) return <div className="px-5 py-4"><LoaderCircle className="animate-spin text-slate-300" size={18} /></div>;
  const c = data.customer;

  return (
    <div className="space-y-4 border-t border-slate-100 px-5 py-4 text-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("Customer")}</p>
        {!editing && <button type="button" className="text-xs text-brand-700 hover:underline" onClick={() => setEditing(true)}>{c ? <><Pencil size={11} className="mr-0.5 inline" /> {t("Edit")}</> : t("Add details")}</button>}
      </div>
      {editing ? (
        <form onSubmit={save} className="space-y-2">
          {FIELDS.map(([k, label]) => (
            <input key={k} className="input py-1.5 text-sm" placeholder={t(label)} aria-label={t(label)} value={(form[k] as string) ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          ))}
          <div className="flex gap-2">
            <button className="btn-primary flex-1 py-1.5" disabled={busy}>{busy ? <LoaderCircle className="animate-spin" size={14} /> : <Check size={14} />} {t("Save")}</button>
            <button type="button" className="btn-ghost py-1.5" onClick={() => setEditing(false)}>{t("Cancel")}</button>
          </div>
        </form>
      ) : c ? (
        <div className="space-y-0.5">
          <Link href={`/customers/${c.id}`} className="font-medium hover:underline">{c.name || t("Unnamed")}</Link>
          {c.phone && <p className="text-slate-600">{c.phone}</p>}
          {(c.address || c.city) && <p className="text-slate-600">{[c.address, c.city, c.district].filter(Boolean).join(", ")}</p>}
          <p className="pt-1 text-xs text-slate-500">{t(c.orders_count === 1 ? "{n} order · {amount} spent" : "{n} orders · {amount} spent", { n: c.orders_count ?? 0, amount: money(c.total_spent ?? 0) })}{(c.contacts?.length ?? 0) > 1 && ` · ${t("on {n} channels", { n: c.contacts!.length })}`}</p>
        </div>
      ) : <p className="text-slate-500">{t("Save their phone and address once and every order is pre-filled.")}</p>}

      <div>
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("Orders")}</p>
          <Link href={`/orders/new?conversation=${conversationId}`} className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline"><Plus size={12} /> {t("New order")}</Link>
        </div>
        {data.orders.length === 0 ? <p className="mt-1 text-slate-500">{t("No orders yet.")}</p> : (
          <ul className="mt-2 space-y-2">
            {data.orders.slice(0, 5).map((o) => (
              <li key={o.id}>
                <Link href={`/orders/${o.id}`} className="block rounded-lg border border-slate-200 p-2 hover:border-brand-300">
                  <span className="flex items-center justify-between"><span className="font-medium">{o.number}</span><span className="font-medium">{money(o.total, o.currency)}</span></span>
                  <span className="mt-1 flex flex-wrap gap-1"><StatusBadge status={o.status} /><PaymentBadge status={o.payment_status} method={o.payment_method} /></span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <Link href={`/orders/new?conversation=${conversationId}`} className="btn-primary mt-3 w-full py-1.5"><ShoppingBag size={14} /> {t("Create order from this chat")}</Link>
      </div>
    </div>
  );
}
