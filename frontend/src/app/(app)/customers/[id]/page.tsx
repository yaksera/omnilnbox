"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Check, GitMerge, LoaderCircle, Plus } from "lucide-react";
import { Api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Customer } from "@/lib/types";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { PaymentBadge, StatusBadge, money } from "@/components/commerce/ui";

const FIELD_LABELS = { name: "Name", phone: "Phone", email: "Email", address: "Address", city: "City", district: "District" } as const;

export default function CustomerPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<Customer | null>(null);
  const [form, setForm] = useState<Partial<Customer>>({});
  const [saved, setSaved] = useState(false);
  const [mergeQ, setMergeQ] = useState("");
  const [matches, setMatches] = useState<Customer[]>([]);
  const [error, setError] = useState("");

  const load = () => Api.customer(id).then((x) => { setC(x); setForm(x); }).catch((e) => setError(e.message));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (mergeQ.trim().length < 2) { setMatches([]); return; }
    const timer = setTimeout(() => Api.customers(mergeQ).then((r) => setMatches(r.filter((x) => x.id !== id).slice(0, 5))), 250);
    return () => clearTimeout(timer);
  }, [mergeQ, id]);

  if (!c) return <div className="flex h-full items-center justify-center">{error ? <p className="text-red-700">{error}</p> : <LoaderCircle className="animate-spin text-slate-400" />}</div>;
  const set = (k: keyof Customer, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    try { await Api.saveCustomer(c!.id, { name: form.name, phone: form.phone, email: form.email, address: form.address, city: form.city, district: form.district, notes: form.notes });
      setSaved(true); setTimeout(() => setSaved(false), 2000); load(); } catch (err) { setError(err instanceof Error ? err.message : t("Failed")); }
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl p-4 sm:p-6">
        <Link href="/customers" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={16} /> {t("Customers")}</Link>
        <div className="mt-2 flex flex-wrap items-end gap-6">
          <div><h1 className="text-xl font-bold">{c.name || t("Unnamed customer")}</h1><p className="text-sm text-slate-500">{t("Customer since {date}", { date: new Date(c.created_at).toLocaleDateString() })}</p></div>
          <div className="ml-auto flex gap-6 text-sm">
            <div><p className="text-xs uppercase text-slate-500">{t("Orders")}</p><p className="text-lg font-bold">{c.orders_count}</p></div>
            <div><p className="text-xs uppercase text-slate-500">{t("Total spent")}</p><p className="text-lg font-bold">{money(c.total_spent ?? 0)}</p></div>
          </div>
        </div>

        <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-5">
            <section className="card p-4">
              <div className="flex items-center justify-between"><h2 className="font-semibold">{t("Orders")}</h2>
                {c.contacts?.[0]?.conversation_id && <Link href={`/orders/new?conversation=${c.contacts[0].conversation_id}`} className="btn-secondary px-3 py-1.5 text-sm"><Plus size={14} /> {t("New order")}</Link>}</div>
              {(c.orders ?? []).length === 0 ? <p className="mt-3 text-sm text-slate-500">{t("No orders yet.")}</p> : (
                <ul className="mt-3 divide-y divide-slate-100">
                  {c.orders!.map((o) => (
                    <li key={o.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                      <Link href={`/orders/${o.id}`} className="font-medium text-brand-700 hover:underline">{o.number}</Link>
                      <span className="text-slate-500">{new Date(o.created_at).toLocaleDateString()}</span>
                      <StatusBadge status={o.status} /><PaymentBadge status={o.payment_status} method={o.payment_method} />
                      <span className="ml-auto font-medium">{money(o.total, o.currency)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="card p-4">
              <h2 className="font-semibold">{t("Chats on every channel")}</h2>
              <ul className="mt-3 space-y-2">
                {(c.contacts ?? []).map((ct) => (
                  <li key={ct.id} className="flex items-center gap-3 text-sm">
                    <ProviderIcon provider={ct.provider} size="sm" />
                    <span className="flex-1">{ct.name || ct.handle} <span className="text-slate-500">· {providerUI(ct.provider).label} ({ct.channel})</span></span>
                    {ct.conversation_id && <Link href={`/inbox?c=${ct.conversation_id}`} className="text-brand-700 hover:underline">{t("Open chat")}</Link>}
                  </li>
                ))}
                {(c.contacts ?? []).length === 0 && <li className="text-sm text-slate-500">{t("Not linked to a chat.")}</li>}
              </ul>
              <div className="mt-4 border-t border-slate-100 pt-3">
                <p className="flex items-center gap-1.5 text-sm font-medium"><GitMerge size={15} /> {t("Same person on another channel?")}</p>
                <p className="text-xs text-slate-500">{t("Search the other profile and merge it into this one. Chats and orders are combined.")}</p>
                <input className="input mt-2" placeholder={t("Search name or phone")} value={mergeQ} onChange={(e) => setMergeQ(e.target.value)} />
                {matches.map((m) => (
                  <button key={m.id} type="button" className="mt-1 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-50"
                    onClick={async () => { if (window.confirm(t("Merge \"{name}\" into this customer?", { name: m.name || m.phone || "" }))) { await Api.mergeCustomer(c.id, m.id); setMergeQ(""); load(); } }}>
                    <span className="flex-1">{m.name || t("Unnamed")} <span className="text-slate-500">{m.phone}</span></span>
                    <span className="flex gap-1">{(m.providers ?? []).map((p) => <ProviderIcon key={p} provider={p} size="xs" />)}</span>
                    <span className="text-xs text-brand-700">{t("Merge")}</span>
                  </button>
                ))}
              </div>
            </section>
          </div>
          <form onSubmit={save} className="card space-y-2 p-4 lg:self-start">
            <h2 className="font-semibold">{t("Details")}</h2>
            {(["name", "phone", "email", "address", "city", "district"] as const).map((k) => (
              <label key={k} className="block text-sm">{t(FIELD_LABELS[k])}<input className="input mt-1" value={(form[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)} type={k === "email" ? "email" : "text"} /></label>
            ))}
            <label className="block text-sm">{t("Notes")}<textarea className="input mt-1 min-h-[70px]" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} placeholder={t("Sizes, preferences, VIP…")} /></label>
            {error && <p className="text-sm text-red-700">{error}</p>}
            <button className="btn-primary w-full">{saved ? <><Check size={15} /> {t("Saved")}</> : t("Save")}</button>
          </form>
        </div>
      </div>
    </div>
  );
}
