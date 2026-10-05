"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CircleAlert, CircleCheck, LoaderCircle, Lock, Store } from "lucide-react";
import { Api } from "@/lib/api";
import type { PublicPayment } from "@/lib/types";
import { money } from "@/components/commerce/ui";
import { translate } from "@/lib/i18n";

const GATEWAY: Record<string, { label: string; color: string }> = {
  khalti: { label: "Pay with Khalti", color: "#5C2D91" },
  esewa: { label: "Pay with eSewa", color: "#60BB46" },
};

function postForm(url: string, fields: Record<string, string>) {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = url;
  for (const [k, v] of Object.entries(fields)) {
    const input = document.createElement("input");
    input.type = "hidden"; input.name = k; input.value = v;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
}

export default function PayPage() {
  const { id } = useParams<{ id: string }>();
  const [lang, setLang] = useState<"en" | "ne">("en");
  useEffect(() => { if (navigator.languages?.some((l) => l.toLowerCase().startsWith("ne"))) setLang("ne"); }, []);
  const t = (s: string, v?: Record<string, string | number>) => translate(lang, s, v);
  const [data, setData] = useState<PublicPayment | null>(null);
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    setResult(new URLSearchParams(window.location.search).get("result") || "");
    Api.publicPayment(id).then(setData).catch(() => setInvalid(true));
  }, [id]);

  async function pay(gateway: string) {
    setBusy(gateway); setError("");
    try {
      const r = await Api.startPayment(id, gateway);
      if (r.redirect_url) window.location.assign(r.redirect_url);
      else if (r.form_url && r.fields) postForm(r.form_url, r.fields);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn't start the payment"));
      setBusy("");
    }
  }

  const paid = data?.status === "paid" || result === "success";

  return (
    <div className="flex min-h-screen items-start justify-center bg-slate-50 px-4 py-10 sm:items-center">
      <div className="w-full max-w-md">
        {!data ? (
          <div className="card p-8 text-center">{invalid ? <p className="text-sm text-red-700">{t("This payment link is not valid.")}</p> : <LoaderCircle className="mx-auto animate-spin text-slate-400" />}</div>
        ) : (
          <div className="card overflow-hidden">
            <div className="flex items-center gap-3 border-b border-slate-100 bg-white p-5">
              {data.brand?.logo_url
                // eslint-disable-next-line @next/next/no-img-element
                ? <img src={data.brand.logo_url} alt="" className="h-10 w-10 rounded-full object-contain" />
                : <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-brand-600"><Store size={20} /></span>}
              <div><p className="font-semibold">{data.shop}</p><p className="text-sm text-slate-500">{t("Order {order}", { order: data.order })}</p></div>
            </div>
            <div className="p-5">
              <ul className="space-y-2 text-sm">
                {data.items.map((i, n) => (
                  <li key={n} className="flex justify-between gap-3"><span>{i.quantity} × {i.name}{i.variant && <span className="text-slate-500"> ({i.variant})</span>}</span><span>{money(i.line_total, data.currency)}</span></li>
                ))}
                {Number(data.delivery_charge) > 0 && <li className="flex justify-between text-slate-600"><span>{t("Delivery")}</span><span>{money(data.delivery_charge, data.currency)}</span></li>}
                {Number(data.discount) > 0 && <li className="flex justify-between text-slate-600"><span>{t("Discount")}</span><span>− {money(data.discount, data.currency)}</span></li>}
              </ul>
              <div className="mt-4 flex items-baseline justify-between border-t border-slate-100 pt-4">
                <span className="text-sm text-slate-600">{t("Total to pay")}</span><span className="text-2xl font-bold">{money(data.amount, data.currency)}</span>
              </div>

              {paid ? (
                <div className="mt-6 rounded-xl bg-emerald-50 p-4 text-center text-emerald-900">
                  <CircleCheck className="mx-auto" size={32} />
                  <p className="mt-2 font-semibold">{t("Payment received. Thank you!")}</p>
                  <p className="text-sm">{t("{shop} has been notified and will prepare your order.", { shop: data.shop })}</p>
                </div>
              ) : (
                <>
                  {result === "failed" && <p className="mt-5 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><CircleAlert size={16} /> {t("The payment wasn't completed. You can try again.")}</p>}
                  <div className="mt-5 space-y-2">
                    {data.gateways.map((g) => (
                      <button key={g} type="button" disabled={!!busy} onClick={() => pay(g)}
                        className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 font-semibold text-white shadow-sm transition hover:opacity-90 disabled:opacity-60"
                        style={{ background: GATEWAY[g]?.color ?? "#4f46e5" }}>
                        {busy === g && <LoaderCircle className="animate-spin" size={18} />} {GATEWAY[g] ? t(GATEWAY[g].label) : g}
                        {data.test_mode[g as "khalti" | "esewa"] && <span className="rounded bg-white/25 px-1.5 text-[10px] uppercase">{t("test")}</span>}
                      </button>
                    ))}
                    {data.gateways.length === 0 && <p className="text-center text-sm text-slate-500">{t("Online payment isn't available for this order. Please contact {shop}.", { shop: data.shop })}</p>}
                  </div>
                  {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
                </>
              )}
              <p className="mt-6 flex items-center justify-center gap-1 text-xs text-slate-400"><Lock size={12} /> {t("Secure payment. You pay {shop} directly through Khalti / eSewa.", { shop: data.shop })}</p>
            </div>
          </div>
        )}
        {!data?.brand?.hide_powered_by && <p className="mt-4 text-center text-xs text-slate-400">{t("Powered by OmniInbox")}</p>}
      </div>
    </div>
  );
}
