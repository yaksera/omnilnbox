import { Check, Search, Send } from "lucide-react";
import { ProviderBadge, ProviderIcon } from "@/lib/providers";

// Illustrative preview of the product UI (sample data, not real customers).
const ROWS = [
  { name: "Aarav S.", provider: "whatsapp", text: "Is the blue hoodie in size M?", time: "now", unread: 2, active: true },
  { name: "maya.creates", provider: "instagram", text: "Do you ship to Pokhara? 😍", time: "2m", unread: 1 },
  { name: "Sita G.", provider: "messenger", text: "What time do you open Saturday?", time: "9m", unread: 1 },
  { name: "Emily Carter", provider: "gmail", text: "Partnership proposal for Q4", time: "18m" },
  { name: "@dancewithkiran", provider: "tiktok", text: "Where can I buy that jacket?", time: "31m" },
  { name: "Bikash R.", provider: "telegram", text: "Payment done via eSewa 🙏", time: "1h" },
];

export default function InboxMockup() {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-white shadow-2xl shadow-black/40 ring-1 ring-black/5">
      <div className="flex items-center gap-1.5 border-b border-slate-200 bg-slate-50 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-red-400" /><span className="h-2.5 w-2.5 rounded-full bg-amber-400" /><span className="h-2.5 w-2.5 rounded-full bg-green-400" />
        <span className="ml-3 truncate text-[11px] text-slate-400">app.omniinbox.com/inbox</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-[240px_1fr]">
        <div className="border-r border-slate-100">
          <div className="p-3">
            <div className="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-400"><Search size={13} /> Search conversations</div>
          </div>
          {ROWS.map((r) => (
            <div key={r.name} className={`flex gap-2.5 border-t border-slate-100 px-3 py-2.5 ${r.active ? "bg-brand-50" : ""}`}>
              <div className="relative">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-600">
                  {r.name.replace(/[@.]/g, "").slice(0, 2).toUpperCase()}
                </span>
                <ProviderIcon provider={r.provider} size="xs" className="absolute -bottom-0.5 -right-0.5 ring-2 ring-white" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex justify-between gap-2"><span className="truncate text-xs font-semibold text-slate-800">{r.name}</span><span className="text-[10px] text-slate-400">{r.time}</span></div>
                <div className="flex items-center gap-1"><p className="flex-1 truncate text-[11px] text-slate-500">{r.text}</p>
                  {r.unread && <span className="rounded-full bg-brand-600 px-1.5 text-[9px] font-bold text-white">{r.unread}</span>}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="hidden flex-col bg-slate-50 sm:flex">
          <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
            <div>
              <p className="text-xs font-semibold text-slate-800">Aarav S.</p>
              <ProviderBadge provider="whatsapp" />
            </div>
            <span className="inline-flex items-center gap-1 rounded-md bg-brand-600 px-2 py-1 text-[10px] font-medium text-white"><Check size={11} /> Close</span>
          </div>
          <div className="flex-1 space-y-2.5 p-4">
            <div className="max-w-[75%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-700">Hi! Is the blue hoodie still available in size M?</div>
            <div className="ml-auto max-w-[75%] rounded-2xl rounded-br-sm bg-brand-600 px-3 py-2 text-[11px] text-white">Yes, size M is in stock! Want me to reserve one for you?</div>
            <div className="max-w-[75%] rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-900">
              <span className="font-semibold">Internal note · Sita:</span> repeat customer, offer free delivery
            </div>
            <div className="max-w-[75%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-700">Yes please! 🙌</div>
          </div>
          <div className="flex items-center gap-2 border-t border-slate-200 bg-white p-3">
            <div className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] text-slate-400">Reply via WhatsApp… type / for saved replies</div>
            <span className="rounded-lg bg-brand-600 p-1.5 text-white"><Send size={12} /></span>
          </div>
        </div>
      </div>
    </div>
  );
}
