"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { LoaderCircle, Package, Plus, Search, Settings2, Users } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { OrderStats, OrderStatus, OrderSummary } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { UpgradeHint, useMe } from "@/components/AppShell";
import { ORDER_STATUS, PaymentBadge, StatusBadge, money } from "@/components/commerce/ui";

const TABS: Array<[string, string]> = [["open", "To do"], ["new", "New"], ["confirmed", "Confirmed"], ["packed", "Packed"],
  ["shipped", "Shipped"], ["delivered", "Delivered"], ["cancelled,returned", "Cancelled"], ["all", "All"]];

function Tile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export default function OrdersPage() {
  const t = useT();
  const { can } = useMe();
  const [tab, setTab] = useState("open");
  const [q, setQ] = useState("");
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [stats, setStats] = useState<OrderStats | null>(null);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      const status = tab === "open" ? "new,confirmed,packed,shipped" : tab;
      Api.orders({ status, q }).then(setOrders).catch((e) => { if (e instanceof ApiError && e.status === 402) setLocked(true); });
    }, 200);
    return () => clearTimeout(timer);
  }, [tab, q]);
  useEffect(() => { Api.orderStats().then(setStats).catch(() => undefined); }, []);

  if (locked) return <div className="mx-auto max-w-2xl p-6"><UpgradeHint feature={t("Orders & payment links")}>{t("Take orders in chat, send Khalti/eSewa payment links and book couriers on the Starter plan and above.")}</UpgradeHint></div>;

  const open = stats ? (["new", "confirmed", "packed"] as OrderStatus[]).reduce((s, k) => s + (stats.by_status[k] ?? 0), 0) : 0;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">{t("Orders")}</h1>
            <p className="text-sm text-slate-500">{t("Take orders from any chat, collect payment and ship, all in one place.")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/products" className="btn-secondary"><Package size={16} /> {t("Products")}</Link>
            <Link href="/customers" className="btn-secondary"><Users size={16} /> {t("Customers")}</Link>
            {can("manage_shop") && <Link href="/settings/shop" className="btn-secondary"><Settings2 size={16} /> {t("Shop settings")}</Link>}
            <Link href="/orders/new" className="btn-primary"><Plus size={16} /> {t("New order")}</Link>
          </div>
        </div>

        {stats && (
          <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile label={t("Orders this month")} value={stats.month_orders} />
            <Tile label={t("Sales this month")} value={money(stats.month_revenue)} sub={t("{amount} collected", { amount: money(stats.month_collected) })} />
            <Tile label={t("To pack & ship")} value={open} sub={t("{n} on the way", { n: stats.by_status.shipped ?? 0 })} />
            <Tile label={t("Awaiting payment")} value={stats.unpaid} sub={t("incl. cash on delivery")} />
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap gap-1">
            {TABS.map(([k, l]) => (
              <button key={k} type="button" onClick={() => { setTab(k); setOrders(null); }}
                className={clsx("rounded-full px-3 py-1 text-xs font-medium", tab === k ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}>{t(l)}</button>
            ))}
          </div>
          <label className="relative ml-auto block w-full sm:w-64">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="input pl-9" placeholder={t("Order #, name, phone, tracking")} value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>

        <div className="card mt-3 overflow-x-auto">
          {orders === null ? <div className="flex justify-center p-8"><LoaderCircle className="animate-spin text-slate-400" /></div>
            : orders.length === 0 ? (
              <div className="p-10 text-center">
                <Package className="mx-auto text-slate-300" size={36} />
                <p className="mt-2 font-medium">{t("No orders here")}</p>
                <p className="text-sm text-slate-500">{t("Create one from a conversation (Inbox → \"New order\") or with the button above.")}</p>
              </div>
            ) : (
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr><th className="px-4 py-2">{t("Order")}</th><th className="px-4 py-2">{t("Customer")}</th><th className="px-4 py-2">{t("Status")}</th>
                    <th className="px-4 py-2">{t("Payment")}</th><th className="px-4 py-2">{t("Delivery")}</th><th className="px-4 py-2 text-right">{t("Total")}</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {orders.map((o) => (
                    <tr key={o.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <Link href={`/orders/${o.id}`} className="font-semibold text-brand-700 hover:underline">{o.number}</Link>
                        {o.source === "ai" && <span className="ml-1.5 rounded-full bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-700">{t("AI")}</span>}
                        <p className="text-xs text-slate-500">{new Date(o.created_at).toLocaleDateString()} · {o.items_count === 1 ? t("{n} item", { n: o.items_count }) : t("{n} items", { n: o.items_count })}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-1.5">{o.provider && <ProviderIcon provider={o.provider} size="xs" />}{o.recipient_name || o.customer?.name || "—"}</span>
                        <p className="text-xs text-slate-500">{o.recipient_phone} {o.city && `· ${o.city}`}</p>
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={o.status} /></td>
                      <td className="px-4 py-3"><PaymentBadge status={o.payment_status} method={o.payment_method} /></td>
                      <td className="px-4 py-3 text-xs text-slate-600">{o.courier_name ? <>{o.courier_name}<br /><span className="text-slate-400">{o.delivery_status || o.tracking_id}</span></> : "—"}</td>
                      <td className="px-4 py-3 text-right font-medium">{money(o.total, o.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>
        <p className="mt-3 text-xs text-slate-400">{t("Status colours: {list}", { list: Object.values(ORDER_STATUS).map((s) => t(s.label)).join(" → ") })}</p>
      </div>
    </div>
  );
}
