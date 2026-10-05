"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import clsx from "clsx";
import { ArrowLeft, CircleCheck, CreditCard, LoaderCircle, MessageSquareText, Store, Truck } from "lucide-react";
import { Api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { ShopSettings, ShopSettingsInput } from "@/lib/types";
import { useMe } from "@/components/AppShell";

/** Fill {placeholders} in an already-translated string with React nodes (bold text). */
function rich(text: string, parts: Record<string, React.ReactNode>) {
  return text.split(/\{(\w+)\}/).map((seg, i) => (i % 2 ? <Fragment key={i}>{parts[seg] ?? `{${seg}}`}</Fragment> : seg));
}

function Card({ icon: Icon, title, desc, children, id }: { icon: typeof Store; title: string; desc: string; children: React.ReactNode; id?: string }) {
  return (
    <section className="card p-5" id={id}>
      <h2 className="flex items-center gap-2 font-semibold"><Icon size={18} /> {title}</h2>
      <p className="mt-1 text-sm text-slate-600">{desc}</p>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function Connected({ on }: { on: boolean }) {
  const t = useT();
  return <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", on ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500")}>{on ? t("Connected") : t("Not connected")}</span>;
}

function Secret({ label, saved, value, onChange, help }: { label: string; saved: boolean; value: string; onChange: (v: string) => void; help?: string }) {
  const t = useT();
  return (
    <label className="block text-sm">{label}
      <input className="input mt-1" type="password" autoComplete="off" value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={saved ? t("Saved. Paste a new value to replace it") : t("Paste here")} />
      {help && <span className="mt-1 block text-xs text-slate-500">{help}</span>}
    </label>
  );
}

function LiveToggle({ live, onChange, name }: { live: boolean; onChange: (v: boolean) => void; name: string }) {
  const t = useT();
  return (
    <div className="flex items-center gap-2 text-sm">
      <span>{t("Mode:")}</span>
      {[false, true].map((v) => (
        <button key={String(v)} type="button" onClick={() => onChange(v)}
          className={clsx("rounded-full border px-3 py-0.5", live === v ? (v ? "border-emerald-500 bg-emerald-50 text-emerald-800" : "border-amber-400 bg-amber-50 text-amber-800") : "border-slate-200 text-slate-500")}>
          {v ? t("Live (real money)") : t("Test / sandbox")}</button>
      ))}
      <span className="sr-only">{name}</span>
    </div>
  );
}

export default function ShopSettingsPage() {
  const t = useT();
  const { can } = useMe();
  const [shop, setShop] = useState<ShopSettings | null>(null);
  const [form, setForm] = useState<ShopSettingsInput>({});
  const [pathao, setPathao] = useState({ client_id: "", client_secret: "", username: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { Api.shopSettings().then((s) => { setShop(s); setForm(s); }).catch(() => undefined); }, []);
  if (!shop) return <div className="flex h-full items-center justify-center"><LoaderCircle className="animate-spin text-slate-400" /></div>;
  if (!can("manage_shop")) return <p className="p-6 text-sm text-slate-500">{t("Only the owner and admins can change shop settings.")}</p>;
  const set = <K extends keyof ShopSettingsInput>(k: K, v: ShopSettingsInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    setBusy(true); setMsg(null);
    const { configured: _c, gateways: _g, couriers: _k, features: _f, ...rest } = form as ShopSettings;
    void _c; void _g; void _k; void _f;
    try {
      const next = await Api.saveShopSettings({ ...rest, pathao });
      setShop(next); setForm(next); setPathao({ client_id: "", client_secret: "", username: "", password: "" });
      setMsg({ ok: true, text: t("Saved.") });
    } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : t("Couldn't save") }); } finally { setBusy(false); }
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-6">
        <Link href="/orders" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={16} /> {t("Orders")}</Link>
        <h1 className="flex items-center gap-2 text-2xl font-bold"><Store size={22} /> {t("Shop settings")}</h1>

        <Card icon={CreditCard} id="payments" title={t("Online payments")} desc={t("Customers pay into YOUR Khalti / eSewa merchant account. OmniInbox never touches the money. We only verify the payment with Khalti/eSewa before marking the order paid.")}>
          <div className="rounded-lg border border-slate-200 p-4">
            <div className="flex items-center justify-between"><p className="font-medium">Khalti</p><Connected on={shop.configured.khalti} /></div>
            <p className="mt-1 text-xs text-slate-500">{rich(t("Khalti merchant dashboard → Keys → {key} (for testing use the key from test-admin.khalti.com and choose Test mode)."), { key: <b>{t("Live secret key")}</b> })}</p>
            <div className="mt-3 space-y-3">
              <Secret label={t("Secret key")} saved={shop.configured.khalti} value={form.khalti_secret_key ?? ""} onChange={(v) => set("khalti_secret_key", v)} />
              <LiveToggle live={!!form.khalti_live} onChange={(v) => set("khalti_live", v)} name="Khalti" />
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 p-4">
            <div className="flex items-center justify-between"><p className="font-medium">eSewa</p><Connected on={shop.configured.esewa} /></div>
            <p className="mt-1 text-xs text-slate-500">{rich(t("Ask eSewa merchant support for your {code} and {key} for ePay v2. In Test mode without keys, eSewa’s public sandbox (EPAYTEST) is used on development servers."), { code: <b>{t("merchant (product) code")}</b>, key: <b>{t("secret key")}</b> })}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="text-sm">{t("Merchant code")}<input className="input mt-1" value={form.esewa_merchant_code ?? ""} onChange={(e) => set("esewa_merchant_code", e.target.value)} /></label>
              <Secret label={t("Secret key")} saved={shop.configured.esewa} value={form.esewa_secret_key ?? ""} onChange={(v) => set("esewa_secret_key", v)} />
            </div>
            <div className="mt-3"><LiveToggle live={!!form.esewa_live} onChange={(v) => set("esewa_live", v)} name="eSewa" /></div>
          </div>
          <label className="block text-sm">{t("Bank transfer / QR details (sent for \"Bank transfer\" orders)")}
            <textarea className="input mt-1 min-h-[70px]" value={form.bank_details ?? ""} onChange={(e) => set("bank_details", e.target.value)} placeholder={"Nabil Bank · Sita Kurta House\nAccount: 0123456789\nFonepay QR: available on request"} />
          </label>
          <label className="block text-sm">{t("How your account appears on payment screenshots (one per line)")}
            <textarea className="input mt-1 min-h-[70px]" value={form.payment_receivers ?? ""} onChange={(e) => set("payment_receivers", e.target.value)} placeholder={"Sita Kurta House\n9801234567\n0123456789"} />
            <span className="mt-1 block text-xs text-slate-500">{t("Your eSewa / Khalti name or number and bank account. The AI flags screenshots paid to anyone else.")}</span>
          </label>
        </Card>

        <Card icon={Truck} id="delivery" title={t("Delivery")} desc={t("Default delivery charges, and courier accounts for booking pickups straight from an order.")}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">{t("Inside Kathmandu Valley (Rs)")}<input className="input mt-1" type="number" min={0} value={form.delivery_inside_valley ?? ""} onChange={(e) => set("delivery_inside_valley", e.target.value)} /></label>
            <label className="text-sm">{t("Outside the Valley (Rs)")}<input className="input mt-1" type="number" min={0} value={form.delivery_outside_valley ?? ""} onChange={(e) => set("delivery_outside_valley", e.target.value)} /></label>
          </div>
          {!shop.features.couriers && <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{t("Booking Nepal Can Move and Pathao from OmniInbox is on the Pro plan and above. On Starter you can still add any courier’s tracking number to an order.")}</p>}
          <div className="rounded-lg border border-slate-200 p-4">
            <div className="flex items-center justify-between"><p className="font-medium">Nepal Can Move (NCM)</p><Connected on={shop.configured.ncm} /></div>
            <p className="mt-1 text-xs text-slate-500">{rich(t("NCM vendor portal → Settings / API → copy your {token}. Test mode uses demo.nepalcanmove.com."), { token: <b>{t("API token")}</b> })}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Secret label={t("API token")} saved={shop.configured.ncm} value={form.ncm_token ?? ""} onChange={(v) => set("ncm_token", v)} />
              <label className="text-sm">{t("Pickup branch")}<input className="input mt-1 uppercase" value={form.ncm_from_branch ?? ""} onChange={(e) => set("ncm_from_branch", e.target.value.toUpperCase())} placeholder="TINKUNE" /></label>
            </div>
            <div className="mt-3"><LiveToggle live={!!form.ncm_live} onChange={(v) => set("ncm_live", v)} name="NCM" /></div>
          </div>
          <div className="rounded-lg border border-slate-200 p-4">
            <div className="flex items-center justify-between"><p className="font-medium">Pathao</p><Connected on={shop.configured.pathao} /></div>
            <p className="mt-1 text-xs text-slate-500">{rich(t("Pathao merchant panel → Developer API → {creds}. Use your merchant login email and password, and your store ID."), { creds: <b>{t("Merchant API credentials")}</b> })}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="text-sm">{t("Client ID")}<input className="input mt-1" value={pathao.client_id} placeholder={shop.configured.pathao ? t("Saved") : ""} onChange={(e) => setPathao({ ...pathao, client_id: e.target.value })} /></label>
              <Secret label={t("Client secret")} saved={shop.configured.pathao} value={pathao.client_secret} onChange={(v) => setPathao({ ...pathao, client_secret: v })} />
              <label className="text-sm">{t("Merchant email")}<input className="input mt-1" type="email" value={pathao.username} placeholder={shop.configured.pathao ? t("Saved") : ""} onChange={(e) => setPathao({ ...pathao, username: e.target.value })} /></label>
              <Secret label={t("Merchant password")} saved={shop.configured.pathao} value={pathao.password} onChange={(v) => setPathao({ ...pathao, password: v })} />
              <label className="text-sm">{t("Store ID")}<input className="input mt-1" value={form.pathao_store_id ?? ""} onChange={(e) => set("pathao_store_id", e.target.value)} /></label>
              <label className="text-sm">{t("API address")}<input className="input mt-1" value={form.pathao_base_url ?? ""} onChange={(e) => set("pathao_base_url", e.target.value)} /></label>
            </div>
          </div>
          <p className="text-xs text-slate-500">{t("Any other courier (Upaya, Aramex, Dash, your own riders): choose \"Other courier\" when shipping and type the tracking number.")}</p>
          <div className="rounded-lg border border-brand-300 bg-brand-50/40 p-4">
            <p className="font-medium">{t("Book the courier automatically")}</p>
            <p className="mt-1 text-xs text-slate-500">{t("Order to doorstep without opening another app: the courier is booked by itself and the customer gets tracking updates in their chat.")}</p>
            <div className="mt-3 grid gap-2">
              {([["off", "Off: my team presses Ship"], ["paid", "When the order is paid online"], ["confirmed", "When the order is confirmed (paid, or cash on delivery)"]] as const).map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-sm">
                  <input type="radio" name="auto_ship" className="accent-brand-600" disabled={!shop.features.couriers && key !== "off"}
                    checked={(form.auto_ship ?? "off") === key} onChange={() => set("auto_ship", key)} /> {t(label)}
                </label>
              ))}
            </div>
            {(form.auto_ship ?? "off") !== "off" && (
              <label className="mt-3 block max-w-xs text-sm">{t("Courier")}
                <select className="input mt-1" value={form.default_courier ?? ""} onChange={(e) => set("default_courier", e.target.value as ShopSettings["default_courier"])}>
                  <option value="">{t("Choose…")}</option>
                  <option value="ncm" disabled={!shop.configured.ncm}>Nepal Can Move{shop.configured.ncm ? "" : ` (${t("not connected")})`}</option>
                  <option value="pathao" disabled={!shop.configured.pathao}>Pathao{shop.configured.pathao ? "" : ` (${t("not connected")})`}</option>
                </select>
                <span className="mt-1 block text-xs text-slate-500">{t("If the address can't be matched (e.g. a Pathao zone), your team gets a note to book it by hand.")}</span>
              </label>
            )}
          </div>
        </Card>

        <Card icon={MessageSquareText} id="messages" title={t("Messages to customers")} desc={t("Sent in the customer’s chat. Placeholders: {list}", { list: "{name} {order} {items} {total} {delivery} {payment} {courier} {tracking} {shop}." })}>
          <label className="block text-sm">{t("Order summary (\"Send order summary\" button)")}<textarea className="input mt-1 min-h-[110px] font-mono text-xs" value={form.msg_order_summary ?? ""} onChange={(e) => set("msg_order_summary", e.target.value)} /></label>
          {([["msg_paid", "auto_message_paid", "When payment is received"], ["msg_shipped", "auto_message_shipped", "When the order ships"], ["msg_out_for_delivery", "auto_message_out_for_delivery", "When it's out for delivery (NCM / Pathao)"], ["msg_delivered", "auto_message_delivered", "When it's delivered"]] as const).map(([msgKey, autoKey, label]) => (
            <div key={msgKey}>
              <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" className="accent-brand-600" checked={!!form[autoKey]} onChange={(e) => set(autoKey, e.target.checked)} /> {t("{label}: send automatically", { label: t(label) })}</label>
              <textarea className="input mt-1 min-h-[60px] font-mono text-xs" value={form[msgKey] ?? ""} onChange={(e) => set(msgKey, e.target.value)} />
            </div>
          ))}
          <label className="block w-40 text-sm">{t("Order number prefix")}<input className="input mt-1" maxLength={10} value={form.order_prefix ?? ""} onChange={(e) => set("order_prefix", e.target.value)} /></label>
        </Card>

        <div className="sticky bottom-0 flex items-center gap-3 border-t border-slate-200 bg-slate-50/95 py-3 backdrop-blur">
          <button type="button" className="btn-primary" onClick={save} disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={16} />} {t("Save shop settings")}</button>
          {msg && <span className={clsx("text-sm", msg.ok ? "text-emerald-700" : "text-red-700")}>{msg.ok && <CircleCheck size={14} className="mr-1 inline" />}{msg.text}</span>}
        </div>
      </div>
    </div>
  );
}
