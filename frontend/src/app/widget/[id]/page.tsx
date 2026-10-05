"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, LoaderCircle, Paperclip, Send, X } from "lucide-react";
import { translate } from "@/lib/i18n";

type Config = { title: string; greeting: string; color: string; ask_contact: "optional" | "required" | "no"; shop: string; online: boolean; max_chars?: number;
  brand?: { logo_url: string; hide_powered_by: boolean } };
type WFile = { id: string; kind: string; name: string; mime: string; size: number; url: string };
type Msg = { id: string; from: "visitor" | "agent" | "bot"; name: string; text: string; at: string; created_at: string; files?: WFile[] };

const BASE = "/backend/widget";

async function call<T>(path: string, init: RequestInit & { token?: string; json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init.token) headers["X-Visitor-Token"] = init.token;
  const res = await fetch(`${BASE}/${path}`, { method: init.method, headers, body: init.json ? JSON.stringify(init.json) : undefined });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || (res.status === 429 ? "You're sending messages too quickly. Please wait a moment." : `Error ${res.status}`));
  }
  return res.json();
}

// Error texts below are stored in English and translated where they are rendered (t(error)).
export default function WidgetPage() {
  const { id } = useParams<{ id: string }>();
  const [lang, setLang] = useState<"en" | "ne">("en");
  useEffect(() => { if (navigator.languages?.some((l) => l.toLowerCase().startsWith("ne"))) setLang("ne"); }, []);
  const t = (s: string, v?: Record<string, string | number>) => translate(lang, s, v);
  const key = `omni.widget.${id}`;
  const [cfg, setCfg] = useState<Config | null>(null);
  const [token, setToken] = useState("");
  const [profile, setProfile] = useState<{ name?: string; phone?: string }>({});
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [form, setForm] = useState({ name: "", phone: "" });
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [embed, setEmbed] = useState(false);
  const last = useRef<string>("");
  const fileInput = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const store = (tok: string, p: typeof profile) => { try { localStorage.setItem(key, JSON.stringify({ t: tok, p })); } catch { /* blocked */ } };

  useEffect(() => {
    setEmbed(new URLSearchParams(window.location.search).get("embed") === "1");
    call<Config>(`${id}/`).then((c) => { setCfg(c); window.parent?.postMessage({ type: "omni:config", color: c.color }, "*"); })
      .catch(() => setError("This chat is not available."));
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved?.t) { setToken(saved.t); setProfile(saved.p || {}); }
    } catch { /* storage blocked */ }
  }, [id, key]);

  const poll = useCallback(async () => {
    if (!token) return;
    const fresh = await call<Msg[]>(`${id}/messages/${last.current ? `?after=${encodeURIComponent(last.current)}` : ""}`, { token }).catch(() => []);
    if (!fresh.length) return;
    last.current = fresh[fresh.length - 1].created_at;
    setMsgs((prev) => {
      const seen = new Set(prev.map((m) => m.id));
      const add = fresh.filter((m) => !seen.has(m.id));
      if (add.some((m) => m.from !== "visitor")) window.parent?.postMessage({ type: "omni:unread" }, "*");
      return [...prev, ...add];
    });
  }, [id, token]);

  useEffect(() => {
    poll();
    const timer = setInterval(() => { if (document.visibilityState === "visible") poll(); }, 4000);
    return () => clearInterval(timer);
  }, [poll]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length]);

  async function ensureSession(p = profile) {
    if (token) return token;
    const r = await call<{ token: string }>(`${id}/session/`, { method: "POST", json: p });
    setToken(r.token); store(r.token, p);
    return r.token;
  }

  async function startWithContact(e: React.FormEvent) {
    e.preventDefault();
    const p = { name: form.name.trim(), phone: form.phone.trim() };
    setProfile(p);
    const r = await call<{ token: string }>(`${id}/session/`, { method: "POST", json: p, token });
    setToken(r.token); store(r.token, p);
  }

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const body = text.trim();
    if (!body || sending) return;
    setSending(true); setError("");
    try {
      const tok = await ensureSession();
      await call(`${id}/messages/`, { method: "POST", token: tok, json: { text: body, name: profile.name || "", contact: profile.phone || "" } });
      setText("");
      await poll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send");
    } finally { setSending(false); }
  }

  async function sendFile(file: File) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { setError("Files can be at most 5 MB."); return; }
    setSending(true); setError("");
    try {
      const tok = await ensureSession();
      const fd = new FormData();
      fd.append("file", file);
      fd.append("text", text.trim());
      if (profile.name) fd.append("name", profile.name);
      const res = await fetch(`${BASE}/${id}/upload/`, { method: "POST", headers: { "X-Visitor-Token": tok }, body: fd });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || (res.status === 429 ? "Please wait a moment." : "Couldn't send the file"));
      setText("");
      await poll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send the file");
    } finally { setSending(false); }
  }

  if (!cfg) return <div className="flex h-screen items-center justify-center bg-white">{error ? <p className="text-sm text-slate-500">{t(error)}</p> : <LoaderCircle className="animate-spin text-slate-400" />}</div>;
  const needContact = cfg.ask_contact !== "no" && !profile.name && !msgs.length;
  const maxChars = cfg.max_chars || 1000;
  const nearLimit = text.length > maxChars * 0.8;
  const required = cfg.ask_contact === "required";

  return (
    <div className={`flex h-screen flex-col bg-white ${embed ? "" : "mx-auto max-w-md border-x border-slate-200"}`}>
      <header className="flex items-center gap-3 px-4 py-3 text-white" style={{ background: cfg.color }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {cfg.brand?.logo_url && <img src={cfg.brand.logo_url} alt="" className="h-8 w-8 rounded-full bg-white object-contain" />}
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{cfg.title}</p>
          <p className="flex items-center gap-1.5 text-xs opacity-90"><span className={`h-2 w-2 rounded-full ${cfg.online ? "bg-emerald-300" : "bg-white/60"}`} />{cfg.shop} · {cfg.online ? t("We're online") : t("We'll reply soon")}</p>
        </div>
        {embed && <button type="button" aria-label={t("Close chat")} onClick={() => window.parent?.postMessage({ type: "omni:close" }, "*")} className="rounded p-1 hover:bg-white/15"><X size={18} /></button>}
      </header>
      <div className="scroll-thin flex-1 space-y-2 overflow-y-auto bg-slate-50 px-3 py-4">
        <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-white px-3 py-2 text-sm text-slate-800 shadow-sm">{cfg.greeting}</div>
        {msgs.map((m) => (
          <div key={m.id} className={`flex ${m.from === "visitor" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm shadow-sm ${m.from === "visitor" ? "rounded-br-sm text-white" : "rounded-bl-sm bg-white text-slate-800"}`}
              style={m.from === "visitor" ? { background: cfg.color } : undefined}>
              {m.files?.map((f) => f.kind === "image"
                // eslint-disable-next-line @next/next/no-img-element
                ? <a key={f.id} href={f.url} target="_blank" rel="noopener noreferrer" className="mb-1 block"><img src={f.url} alt={f.name} className="max-h-56 rounded-lg" /></a>
                : f.kind === "video" ? <video key={f.id} src={f.url} controls className="mb-1 max-h-56 rounded-lg" />
                : f.kind === "audio" || f.kind === "voice" ? <audio key={f.id} src={f.url} controls className="mb-1 h-9 w-56" />
                : <a key={f.id} href={`${f.url}?download=1`} className="mb-1 flex items-center gap-2 rounded-lg bg-black/5 px-2 py-1.5 text-xs underline-offset-2 hover:underline"><FileText size={16} /> {f.name || t("File")}</a>)}
              {m.text && !/^\[(image|file|attachment)\]$/.test(m.text) && m.text}
            </div>
          </div>
        ))}
        {needContact && (
          <form onSubmit={startWithContact} className="space-y-2 rounded-xl bg-white p-3 shadow-sm">
            <p className="text-xs text-slate-600">{required ? t("Please tell us your name and phone so we can help you.") : t("Leave your name and phone so we can reach you (optional).")}</p>
            <input className="input py-1.5 text-sm" placeholder={t("Your name")} required={required} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="input py-1.5 text-sm" placeholder={t("Phone (98XXXXXXXX)")} inputMode="tel" required={required} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <button className="w-full rounded-lg py-1.5 text-sm font-medium text-white" style={{ background: cfg.color }}>{t("Start chat")}</button>
          </form>
        )}
        <div ref={bottom} />
      </div>
      {error && <p className="bg-red-50 px-3 py-1 text-xs text-red-700">{t(error)}</p>}
      {nearLimit && <p className={`px-3 pt-1 text-right text-[11px] ${text.length >= maxChars ? "text-red-600" : "text-slate-400"}`}>{text.length}/{maxChars}</p>}
      <form onSubmit={send} className="flex items-end gap-2 border-t border-slate-200 p-2">
        <button type="button" onClick={() => fileInput.current?.click()} disabled={sending || (needContact && required)} aria-label={t("Send a photo")}
          title={t("Send a photo or PDF (max 5 MB)")} className="flex h-10 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 disabled:opacity-50">
          <Paperclip size={17} />
        </button>
        <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) sendFile(f); }} />
        <textarea className="input max-h-28 min-h-[40px] flex-1 resize-none text-sm" rows={1} placeholder={t("Type your message…")} value={text} maxLength={maxChars}
          disabled={needContact && required}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <button className="flex h-10 w-10 items-center justify-center rounded-full text-white disabled:opacity-50" style={{ background: cfg.color }} disabled={sending || !text.trim()} aria-label={t("Send")}>
          {sending ? <LoaderCircle className="animate-spin" size={16} /> : <Send size={16} />}
        </button>
      </form>
      {!cfg.brand?.hide_powered_by && <p className="pb-1 text-center text-[10px] text-slate-400">{t("Powered by OmniInbox")}</p>}
    </div>
  );
}
