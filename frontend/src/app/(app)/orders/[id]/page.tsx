"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useEffect, useState } from "react";
import clsx from "clsx";
import {
  ArrowLeft, Check, CircleAlert, Copy, CreditCard, ExternalLink, History, LoaderCircle, MessageCircle, Package, Pencil,
  Send, Truck, X,
} from "lucide-react";
import { Api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Order, OrderStatus, ShopSettings } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { useMe } from "@/components/AppShell";
import OrderEditor from "@/components/commerce/OrderEditor";
import { ORDER_STATUS, PAYMENT_METHOD, PaymentBadge, STATUS_FLOW, StatusBadge, money } from "@/components/commerce/ui";

type Named = { id: number; name: string };

/** Fill {placeholders} in an already-translated string with React nodes (links, bold text). */
function rich(text: string, parts: Record<string, React.ReactNode>) {
  return text.split(/\{(\w+)\}/).map((seg, i) => (i % 2 ? <Fragment key={i}>{parts[seg] ?? `{${seg}}`}</Fragment> : seg));
}

function ShipDialog({ order, shop, onDone, onClose }: { order: Order; shop: ShopSettings; onDone: (o: Order) => void; onClose: () => void }) {
  const t = useT();
  const { hasFeature } = useMe();
  const canBook = hasFeature("courier_integrations");
  const options = [
    ...(canBook && shop.couriers.includes("ncm") ? [["ncm", "Nepal Can Move"]] : []),
    ...(canBook && shop.couriers.includes("pathao") ? [["pathao", "Pathao"]] : []),
    ["manual", "Other courier"], ["self", "Own delivery"],
  ] as Array<[string, string]>;
  const [courier, setCourier] = useState(options[0][0]);
  const [opts, setOpts] = useState<Record<string, string>>({ weight: "1" });
  const [branches, setBranches] = useState<Array<{ name: string; district: string }>>([]);
  const [cities, setCities] = useState<Named[]>([]);
  const [zones, setZones] = useState<Named[]>([]);
  const [areas, setAreas] = useState<Named[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: string, v: string) => setOpts((o) => ({ ...o, [k]: v }));

  useEffect(() => {
    setError("");
    if (courier === "ncm" && !branches.length) {
      Api.courierLookup<Array<{ name: string; district: string }>>("ncm", "branches").then((b) => {
        setBranches(b);
        const guess = b.find((x) => [order.district, order.city].some((w) => w && (x.district || x.name).toLowerCase() === w.toLowerCase()));
        if (guess) set("branch", guess.name);
      }).catch((e) => setError(e.message));
    }
    if (courier === "pathao" && !cities.length) Api.courierLookup<Named[]>("pathao", "cities").then(setCities).catch((e) => setError(e.message));
  }, [courier, branches.length, cities.length, order.city, order.district]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try { onDone(await Api.orderAction(order.id, "ship", { courier, ...opts })); } catch (err) { setError(err instanceof Error ? err.message : t("Failed")); } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true">
      <form onSubmit={submit} className="card w-full max-w-lg space-y-4 p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-semibold"><Truck size={18} /> {t("Ship order {number}", { number: order.number })}</h2>
          <button type="button" className="btn-ghost px-2" onClick={onClose} aria-label={t("Close")}><X size={16} /></button>
        </div>
        <div className="flex flex-wrap gap-2">
          {options.map(([k, l]) => (
            <button key={k} type="button" onClick={() => setCourier(k)}
              className={clsx("rounded-full border px-3 py-1 text-sm", courier === k ? "border-brand-500 bg-brand-50 text-brand-800" : "border-slate-200 text-slate-600")}>{t(l)}</button>
          ))}
        </div>
        {!canBook && <p className="text-xs text-slate-500">{t("Booking Nepal Can Move / Pathao directly is on Pro and above. You can still add any courier’s tracking number.")}</p>}
        {canBook && !shop.couriers.length && <p className="text-xs text-slate-500">{rich(t("Connect Nepal Can Move or Pathao in {link} to book pickups from here."), { link: <Link href="/settings/shop" className="text-brand-700 underline">{t("Shop settings")}</Link> })}</p>}
        <p className="rounded-lg bg-slate-50 p-2 text-xs text-slate-600">{t("To:")} <b>{order.recipient_name || "—"}</b>, {order.recipient_phone || t("no phone")}, {order.address}{order.city && `, ${order.city}`}. {t("Cash to collect:")} <b>{order.payment_status === "paid" ? t("nothing (paid)") : money(order.total)}</b></p>

        {courier === "ncm" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm sm:col-span-2">{t("Destination branch")}
              <select className="input mt-1" required value={opts.branch ?? ""} onChange={(e) => set("branch", e.target.value)}>
                <option value="">{t("Choose…")}</option>
                {branches.map((b) => <option key={b.name} value={b.name}>{b.name}{b.district && ` (${b.district})`}</option>)}
              </select>
            </label>
            <label className="text-sm">{t("Weight (kg)")}<input className="input mt-1" type="number" min="0.1" step="0.1" value={opts.weight} onChange={(e) => set("weight", e.target.value)} /></label>
            <label className="text-sm">{t("Delivery type")}
              <select className="input mt-1" value={opts.delivery_type ?? "Door2Door"} onChange={(e) => set("delivery_type", e.target.value)}>
                <option value="Door2Door">{t("Door to door")}</option><option value="Branch2Door">{t("Branch to door")}</option>
                <option value="Door2Branch">{t("Door to branch")}</option><option value="Branch2Branch">{t("Branch to branch")}</option>
              </select>
            </label>
          </div>
        )}
        {courier === "pathao" && (
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm">{t("City")}
              <select className="input mt-1" required value={opts.city_id ?? ""} onChange={(e) => { set("city_id", e.target.value); setZones([]); setAreas([]); Api.courierLookup<Named[]>("pathao", "zones", `city=${e.target.value}`).then(setZones).catch((er) => setError(er.message)); }}>
                <option value="">{t("Choose…")}</option>{cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label className="text-sm">{t("Zone")}
              <select className="input mt-1" required value={opts.zone_id ?? ""} onChange={(e) => { set("zone_id", e.target.value); Api.courierLookup<Named[]>("pathao", "areas", `zone=${e.target.value}`).then(setAreas).catch(() => setAreas([])); }}>
                <option value="">{t("Choose…")}</option>{zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
              </select>
            </label>
            <label className="text-sm">{t("Area")}
              <select className="input mt-1" value={opts.area_id ?? ""} onChange={(e) => set("area_id", e.target.value)}>
                <option value="">{t("Optional")}</option>{areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <label className="text-sm">{t("Weight (kg)")}<input className="input mt-1" type="number" min="0.1" step="0.1" value={opts.weight} onChange={(e) => set("weight", e.target.value)} /></label>
          </div>
        )}
        {(courier === "manual" || courier === "self") && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">{courier === "self" ? t("Rider / note") : t("Courier name")}
              <input className="input mt-1" placeholder={courier === "self" ? t("e.g. Ramesh (rider)") : t("e.g. Upaya, Aramex, Dash")} value={opts.courier_name ?? ""} onChange={(e) => set("courier_name", e.target.value)} />
            </label>
            <label className="text-sm">{t("Tracking number")}<input className="input mt-1" value={opts.tracking_id ?? ""} onChange={(e) => set("tracking_id", e.target.value)} /></label>
            <label className="text-sm sm:col-span-2">{t("Tracking link (optional)")}<input className="input mt-1" type="url" placeholder="https://" value={opts.tracking_url ?? ""} onChange={(e) => set("tracking_url", e.target.value)} /></label>
          </div>
        )}
        {courier !== "self" && <label className="block text-sm">{t("Instructions for the courier")}<input className="input mt-1" maxLength={200} value={opts.instruction ?? ""} placeholder={t("Call before delivery")} onChange={(e) => set("instruction", e.target.value)} /></label>}
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn-primary" disabled={busy}>{busy ? <LoaderCircle className="animate-spin" size={16} /> : <Truck size={16} />} {courier === "ncm" || courier === "pathao" ? t("Book pickup") : t("Mark as shipped")}</button>
        </div>
        {order.conversation_id && <p className="text-xs text-slate-500">{t("The customer gets the \"order shipped\" message with the tracking info (change it in Shop settings).")}</p>}
      </form>
    </div>
  );
}

export default function OrderPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const [order, setOrder] = useState<Order | null>(null);
  const [shop, setShop] = useState<ShopSettings | null>(null);
  const [editing, setEditing] = useState(false);
  const [shipping, setShipping] = useState(false);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    Api.order(id).then(setOrder).catch((e) => setMsg({ ok: false, text: e.message }));
    Api.shopSettings().then(setShop).catch(() => undefined);
  }, [id]);

  async function act(key: string, fn: () => Promise<Order>, ok: string) {
    setBusy(key); setMsg(null);
    try { setOrder(await fn()); setMsg({ ok: true, text: ok }); } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : t("Failed") }); } finally { setBusy(""); }
  }

  if (!order || !shop) return <div className="flex h-full items-center justify-center">{msg ? <p className="text-sm text-red-700">{msg.text}</p> : <LoaderCircle className="animate-spin text-slate-400" />}</div>;

  const next = STATUS_FLOW[STATUS_FLOW.indexOf(order.status) + 1] as OrderStatus | undefined;
  const link = order.payment_links.find((l) => l.status === "pending");
  const closed = ["delivered", "cancelled", "returned"].includes(order.status);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <Link href="/orders" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={16} /> {t("Orders")}</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="flex items-center gap-2 text-xl font-bold">{t("Order {number}", { number: order.number })}
            {order.source === "ai" && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-xs font-medium text-violet-700">{t("Taken by AI")}</span>}</h1>
          <StatusBadge status={order.status} /><PaymentBadge status={order.payment_status} method={order.payment_method} />
          <span className="text-sm text-slate-500">{new Date(order.created_at).toLocaleString()}{order.created_by && ` · ${t("by {name}", { name: order.created_by })}`}</span>
          <div className="ml-auto flex flex-wrap gap-2">
            {order.conversation_id && <Link href={`/inbox?c=${order.conversation_id}`} className="btn-secondary">{order.provider && <ProviderIcon provider={order.provider} size="xs" />} {t("Open chat")}</Link>}
            {!editing && !closed && <button type="button" className="btn-secondary" onClick={() => setEditing(true)}><Pencil size={15} /> {t("Edit")}</button>}
          </div>
        </div>

        {/* progress */}
        {!["cancelled", "returned"].includes(order.status) && (
          <ol className="mt-5 flex items-center gap-1 overflow-x-auto text-xs">
            {STATUS_FLOW.map((s, i) => {
              const done = STATUS_FLOW.indexOf(order.status) >= i;
              return (
                <li key={s} className="flex min-w-[90px] flex-1 items-center gap-1">
                  <span className={clsx("flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold", done ? "bg-brand-600 text-white" : "bg-slate-200 text-slate-500")}>{done ? <Check size={13} /> : i + 1}</span>
                  <span className={done ? "font-medium text-slate-800" : "text-slate-400"}>{t(ORDER_STATUS[s].label)}</span>
                  {i < STATUS_FLOW.length - 1 && <span className={clsx("h-px flex-1", done ? "bg-brand-300" : "bg-slate-200")} />}
                </li>
              );
            })}
          </ol>
        )}

        {msg && <p className={clsx("mt-4 flex items-center gap-2 rounded-lg px-3 py-2 text-sm", msg.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-700")}>{msg.ok ? <Check size={15} /> : <CircleAlert size={15} />} {msg.text}</p>}

        {editing ? (
          <div className="mt-5">
            <OrderEditor initial={order} shop={shop} />
            <button type="button" className="btn-ghost mt-3" onClick={() => setEditing(false)}>{t("Cancel editing")}</button>
          </div>
        ) : (
          <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_340px]">
            <div className="space-y-5">
              <section className="card">
                <div className="divide-y divide-slate-100">
                  {order.items.map((i) => (
                    <div key={i.id} className="flex items-center gap-3 p-4">
                      <span className="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-slate-100">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        {i.image_url ? <img src={i.image_url} alt="" className="h-full w-full object-cover" /> : <Package size={18} className="m-3.5 text-slate-400" />}
                      </span>
                      <div className="min-w-0 flex-1"><p className="font-medium">{i.name}</p><p className="text-xs text-slate-500">{i.variant && `${i.variant} · `}{i.quantity} × {money(i.unit_price, order.currency)}</p></div>
                      <p className="font-medium">{money(i.line_total ?? 0, order.currency)}</p>
                    </div>
                  ))}
                </div>
                <dl className="space-y-1 border-t border-slate-100 p-4 text-sm">
                  <div className="flex justify-between"><dt className="text-slate-500">{t("Subtotal")}</dt><dd>{money(order.subtotal, order.currency)}</dd></div>
                  <div className="flex justify-between"><dt className="text-slate-500">{t("Delivery")}</dt><dd>{money(order.delivery_charge, order.currency)}</dd></div>
                  {Number(order.discount) > 0 && <div className="flex justify-between"><dt className="text-slate-500">{t("Discount")}</dt><dd>− {money(order.discount, order.currency)}</dd></div>}
                  <div className="flex justify-between pt-1 text-base font-semibold"><dt>{t("Total")}</dt><dd>{money(order.total, order.currency)}</dd></div>
                </dl>
              </section>

              <section className="card p-4">
                <h2 className="font-semibold">{t("Deliver to")}</h2>
                <p className="mt-2 text-sm">{order.recipient_name || "—"} · {order.recipient_phone || t("no phone")}</p>
                <p className="text-sm text-slate-600">{[order.address, order.city, order.district].filter(Boolean).join(", ") || t("No address yet")}</p>
                {order.note && <p className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-900">📝 {order.note}</p>}
                {order.customer && <Link href={`/customers/${order.customer.id}`} className="mt-2 inline-block text-sm text-brand-700 hover:underline">{t("View customer profile →")}</Link>}
              </section>

              <section className="card p-4">
                <h2 className="flex items-center gap-2 font-semibold"><History size={16} /> {t("History")}</h2>
                <ol className="mt-3 space-y-2 border-l border-slate-200 pl-4">
                  {[...order.history].reverse().map((h, i) => (
                    <li key={i} className="relative text-sm"><span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-brand-500" />
                      {h.text}<span className="block text-xs text-slate-400">{new Date(h.at).toLocaleString()} · {h.by}</span></li>
                  ))}
                </ol>
              </section>
            </div>

            <aside className="space-y-4">
              {order.conversation_id && (
                <section className="card p-4">
                  <h2 className="flex items-center gap-2 font-semibold"><MessageCircle size={16} /> {t("Customer chat")}</h2>
                  <p className="mt-1 text-xs text-slate-500">{order.payment_method === "khalti" || order.payment_method === "esewa"
                    ? t("Sends the items, total and payment instructions with a payment link to the customer on {app}.", { app: order.provider ?? t("their app") })
                    : t("Sends the items, total and payment instructions to the customer on {app}.", { app: order.provider ?? t("their app") })}</p>
                  <button type="button" className="btn-primary mt-3 w-full" disabled={!!busy}
                    onClick={() => act("summary", () => Api.orderAction(order.id, "send-summary"), t("Order summary sent to the customer."))}>
                    {busy === "summary" ? <LoaderCircle className="animate-spin" size={15} /> : <Send size={15} />} {t("Send order summary")}
                  </button>
                </section>
              )}

              <section className="card space-y-3 p-4">
                <h2 className="flex items-center gap-2 font-semibold"><CreditCard size={16} /> {t("Payment")}</h2>
                <p className="text-sm">{t(PAYMENT_METHOD[order.payment_method])} · <PaymentBadge status={order.payment_status} method={order.payment_method} /></p>
                {order.paid_at && <p className="text-xs text-slate-500">{t("Paid {date}", { date: new Date(order.paid_at).toLocaleString() })}</p>}
                {order.payment_status !== "paid" && (
                  <>
                    {link ? (
                      <div className="flex items-center gap-2 rounded-lg bg-slate-50 p-2">
                        <code className="min-w-0 flex-1 truncate text-xs">{link.url}</code>
                        <button type="button" className="btn-ghost px-2" aria-label={t("Copy link")} onClick={() => { navigator.clipboard.writeText(link.url); setMsg({ ok: true, text: t("Payment link copied.") }); }}><Copy size={14} /></button>
                        <a href={link.url} target="_blank" rel="noreferrer" className="btn-ghost px-2" aria-label={t("Open payment page")}><ExternalLink size={14} /></a>
                      </div>
                    ) : null}
                    {shop.gateways.length > 0 ? (
                      <button type="button" className="btn-secondary w-full" disabled={!!busy}
                        onClick={() => act("link", () => Api.orderAction(order.id, "payment-link", { send: !!order.conversation_id }), order.conversation_id ? t("Payment link sent in the chat.") : t("Payment link created. Copy it and send it to the customer."))}>
                        {busy === "link" && <LoaderCircle className="animate-spin" size={15} />} {order.conversation_id ? t("Send Khalti / eSewa link") : t("Create payment link")}
                      </button>
                    ) : <p className="text-xs text-slate-500">{rich(t("Connect Khalti or eSewa in {link} to send payment links."), { link: <Link href="/settings/shop" className="text-brand-700 underline">{t("Shop settings")}</Link> })}</p>}
                    <button type="button" className="btn-ghost w-full" disabled={!!busy}
                      onClick={() => act("paid", () => Api.orderAction(order.id, "mark-paid"), t("Marked as paid."))}>{t("Mark as paid (cash / bank / QR)")}</button>
                  </>
                )}
              </section>

              <section className="card space-y-3 p-4">
                <h2 className="flex items-center gap-2 font-semibold"><Truck size={16} /> {t("Delivery")}</h2>
                {order.courier_name ? (
                  <div className="text-sm">
                    <p className="font-medium">{order.courier_name}</p>
                    {order.tracking_id && <p className="text-slate-600">{t("Tracking:")} <b>{order.tracking_id}</b></p>}
                    {order.delivery_status && <p className="text-slate-600">{t("Status: {status}", { status: order.delivery_status })}</p>}
                    {order.tracking_url && <a href={order.tracking_url} target="_blank" rel="noreferrer" className="text-brand-700 hover:underline">{t("Track parcel →")}</a>}
                  </div>
                ) : <p className="text-sm text-slate-500">{t("Not shipped yet.")}</p>}
                {!order.courier_name && !closed && <button type="button" className="btn-primary w-full" onClick={() => setShipping(true)}><Truck size={15} /> {t("Ship this order")}</button>}
              </section>

              <section className="card space-y-2 p-4">
                <h2 className="font-semibold">{t("Status")}</h2>
                {next && next !== "shipped" && !closed && (
                  <button type="button" className="btn-secondary w-full" disabled={!!busy}
                    onClick={() => act("status", () => Api.orderAction(order.id, "status", { status: next }), t("Marked as {status}.", { status: t(ORDER_STATUS[next].label).toLowerCase() }))}>
                    {t("Mark as {status}", { status: t(ORDER_STATUS[next].label).toLowerCase() })}
                  </button>
                )}
                <select className="input" value={order.status} aria-label={t("Change status")}
                  onChange={(e) => act("status", () => Api.orderAction(order.id, "status", { status: e.target.value }), t("Status updated."))}>
                  {(Object.keys(ORDER_STATUS) as OrderStatus[]).map((s) => <option key={s} value={s}>{t(ORDER_STATUS[s].label)}</option>)}
                </select>
              </section>
            </aside>
          </div>
        )}
      </div>
      {shipping && <ShipDialog order={order} shop={shop} onClose={() => setShipping(false)} onDone={(o) => { setOrder(o); setShipping(false); setMsg({ ok: true, text: t("Shipped with {courier}.", { courier: o.courier_name ?? "" }) }); }} />}
    </div>
  );
}
