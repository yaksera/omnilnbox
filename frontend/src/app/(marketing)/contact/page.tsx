"use client";

import { useState } from "react";
import { CircleCheck, LoaderCircle, Mail, MessageCircle } from "lucide-react";
import { Api } from "@/lib/api";

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", company: "", phone: "", message: "" });
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setError("");
    try {
      await Api.contactSales(form);
      setState("sent");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send. Please try again.");
      setState("idle");
    }
  }

  return (
    <section className="bg-white">
      <div className="mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">Contact sales</p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900">Let&apos;s talk about your team</h1>
          <p className="mt-4 text-lg text-slate-600">
            Enterprise plans, custom limits, onboarding help or a live demo. Tell us what you need and we&apos;ll reply within one business day.
          </p>
          <div className="mt-8 space-y-4 text-sm text-slate-700">
            <p className="flex items-center gap-3"><Mail className="text-brand-600" size={20} /> sales@omniinbox.app</p>
            <p className="flex items-center gap-3"><MessageCircle className="text-brand-600" size={20} /> Or message us from inside the app</p>
          </div>
        </div>
        <div className="card p-6">
          {state === "sent" ? (
            <div className="py-10 text-center">
              <CircleCheck className="mx-auto text-emerald-600" size={40} />
              <p className="mt-4 text-lg font-semibold">Thanks, we got your message.</p>
              <p className="mt-1 text-sm text-slate-600">We&apos;ll get back to you at {form.email} soon.</p>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm"><span className="mb-1 block font-medium text-slate-700">Name</span><input className="input" required value={form.name} onChange={set("name")} /></label>
                <label className="text-sm"><span className="mb-1 block font-medium text-slate-700">Work email</span><input className="input" type="email" required value={form.email} onChange={set("email")} /></label>
                <label className="text-sm"><span className="mb-1 block font-medium text-slate-700">Company</span><input className="input" value={form.company} onChange={set("company")} /></label>
                <label className="text-sm"><span className="mb-1 block font-medium text-slate-700">Phone</span><input className="input" value={form.phone} onChange={set("phone")} /></label>
              </div>
              <label className="block text-sm"><span className="mb-1 block font-medium text-slate-700">How can we help?</span>
                <textarea className="input min-h-[120px]" required value={form.message} onChange={set("message")} placeholder="Team size, channels you use, anything else…" />
              </label>
              {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
              <button className="btn-primary w-full" disabled={state === "sending"}>
                {state === "sending" && <LoaderCircle className="animate-spin" size={16} />} Send message
              </button>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
