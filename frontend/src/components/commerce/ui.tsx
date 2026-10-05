import clsx from "clsx";
import type { OrderStatus, PaymentMethod, PaymentStatus } from "@/lib/types";
import { money as fmt } from "@/lib/money";
import { useT } from "@/lib/i18n";

export const money = (amount: string | number, currency = "NPR") => fmt(amount, currency === "USD" ? "USD" : "NPR");

export const ORDER_STATUS: Record<OrderStatus, { label: string; cls: string }> = {
  new: { label: "New", cls: "bg-sky-50 text-sky-700 ring-sky-200" },
  confirmed: { label: "Confirmed", cls: "bg-indigo-50 text-indigo-700 ring-indigo-200" },
  packed: { label: "Packed", cls: "bg-violet-50 text-violet-700 ring-violet-200" },
  shipped: { label: "Shipped", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
  delivered: { label: "Delivered", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  cancelled: { label: "Cancelled", cls: "bg-slate-100 text-slate-500 ring-slate-200" },
  returned: { label: "Returned", cls: "bg-red-50 text-red-700 ring-red-200" },
};
export const STATUS_FLOW: OrderStatus[] = ["new", "confirmed", "packed", "shipped", "delivered"];

export const PAYMENT_METHOD: Record<PaymentMethod, string> = {
  cod: "Cash on delivery", khalti: "Khalti", esewa: "eSewa", bank: "Bank transfer / QR", cash: "Cash (in store)",
};
export const PAYMENT_STATUS: Record<PaymentStatus, { label: string; cls: string }> = {
  unpaid: { label: "Unpaid", cls: "bg-slate-100 text-slate-600" },
  pending: { label: "Link sent", cls: "bg-amber-50 text-amber-800" },
  paid: { label: "Paid", cls: "bg-emerald-50 text-emerald-700" },
  refunded: { label: "Refunded", cls: "bg-red-50 text-red-700" },
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  const t = useT();
  const s = ORDER_STATUS[status];
  return <span className={clsx("inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", s.cls)}>{t(s.label)}</span>;
}

export function PaymentBadge({ status, method }: { status: PaymentStatus; method?: PaymentMethod }) {
  const t = useT();
  const s = PAYMENT_STATUS[status];
  const label = status === "unpaid" && method === "cod" ? "COD" : s.label;
  return <span className={clsx("inline-flex rounded-full px-2 py-0.5 text-xs font-medium", s.cls)}>{t(label)}</span>;
}

export const DISTRICTS_VALLEY = ["Kathmandu", "Lalitpur", "Bhaktapur"];
