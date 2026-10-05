"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LoaderCircle, Search, Users } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Customer } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { avatarColor, initials } from "@/lib/format";
import { UpgradeHint } from "@/components/AppShell";
import { money } from "@/components/commerce/ui";

export default function CustomersPage() {
  const t = useT();
  const [rows, setRows] = useState<Customer[] | null>(null);
  const [q, setQ] = useState("");
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => Api.customers(q).then(setRows).catch((e) => { if (e instanceof ApiError && e.status === 402) setLocked(true); }), 200);
    return () => clearTimeout(timer);
  }, [q]);

  if (locked) return <div className="mx-auto max-w-2xl p-6"><UpgradeHint feature={t("Customer profiles")}>{t("See every customer’s orders and chats across all channels on Starter and above.")}</UpgradeHint></div>;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <div><h1 className="text-xl font-bold">{t("Customers")}</h1>
            <p className="text-sm text-slate-500">{t("One profile per person, even if they message you on WhatsApp, Instagram and Messenger.")}</p></div>
          <label className="relative ml-auto block w-full sm:w-72"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="input pl-9" placeholder={t("Name, phone, email, city")} value={q} onChange={(e) => setQ(e.target.value)} /></label>
        </div>
        <div className="card mt-5 overflow-x-auto">
          {rows === null ? <div className="flex justify-center p-8"><LoaderCircle className="animate-spin text-slate-400" /></div> : rows.length === 0 ? (
            <div className="p-10 text-center"><Users className="mx-auto text-slate-300" size={36} /><p className="mt-2 font-medium">{t("No customers yet")}</p>
              <p className="text-sm text-slate-500">{t("Customers are created automatically when you save their details or an order from a conversation.")}</p></div>
          ) : (
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                <tr><th className="px-4 py-2">{t("Customer")}</th><th className="px-4 py-2">{t("Channels")}</th><th className="px-4 py-2">{t("Location")}</th><th className="px-4 py-2 text-right">{t("Orders")}</th><th className="px-4 py-2 text-right">{t("Spent")}</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link href={`/customers/${c.id}`} className="flex items-center gap-3">
                        <span className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold text-white" style={{ background: avatarColor(c.id) }}>{initials(c.name || c.phone || "?")}</span>
                        <span><span className="block font-medium text-slate-900 hover:underline">{c.name || t("Unnamed")}</span><span className="text-xs text-slate-500">{c.phone || c.email}</span></span>
                      </Link>
                    </td>
                    <td className="px-4 py-3"><span className="flex gap-1">{(c.providers ?? []).map((p) => <ProviderIcon key={p} provider={p} size="xs" />)}</span></td>
                    <td className="px-4 py-3 text-slate-600">{[c.city, c.district].filter(Boolean).join(", ") || "—"}</td>
                    <td className="px-4 py-3 text-right">{c.orders_count}</td>
                    <td className="px-4 py-3 text-right font-medium">{money(c.total_spent ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
