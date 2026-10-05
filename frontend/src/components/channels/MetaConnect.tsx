"use client";

import { useEffect, useRef, useState } from "react";
import { CircleCheck, LoaderCircle, X } from "lucide-react";
import { SiFacebook } from "react-icons/si";
import { Api } from "@/lib/api";
import type { MetaConfig, MetaPage } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { useT } from "@/lib/i18n";

/* Minimal typing for the Facebook JS SDK. */
type FBLoginResponse = { authResponse?: { code?: string; accessToken?: string } | null; status?: string };
export type FBSdk = {
  init: (o: { appId: string; version: string; xfbml: boolean; autoLogAppEvents?: boolean }) => void;
  login: (cb: (r: FBLoginResponse) => void, o: Record<string, unknown>) => void;
};
declare global { interface Window { FB?: FBSdk; fbAsyncInit?: () => void } }

let sdkPromise: Promise<FBSdk> | null = null;
export function loadSdk(appId: string, version: string): Promise<FBSdk> {
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<FBSdk>((resolve, reject) => {
    window.fbAsyncInit = () => {
      window.FB!.init({ appId, version, xfbml: false, autoLogAppEvents: true });
      resolve(window.FB!);
    };
    const s = document.createElement("script");
    s.src = "https://connect.facebook.net/en_US/sdk.js";
    s.async = true;
    s.crossOrigin = "anonymous";
    s.onerror = () => { sdkPromise = null; reject(new Error("Couldn't load Facebook. Check your connection or ad blocker.")); };
    document.body.appendChild(s);
  });
  return sdkPromise;
}

export function fbLogin(sdk: FBSdk, options: Record<string, unknown>, want: "code" | "accessToken" = "code") {
  return new Promise<string>((resolve, reject) => {
    sdk.login((r) => {  // the SDK needs a plain (non-async) callback
      const value = r.authResponse?.[want];
      if (value) resolve(value);
      else reject(new Error("The Facebook window was closed before finishing."));
    }, options);
  });
}

export function useMetaConfig() {
  const [cfg, setCfg] = useState<MetaConfig | null>(null);
  useEffect(() => { Api.metaConfig().then(setCfg).catch(() => setCfg(null)); }, []);
  return cfg;
}

/** "Connect with Facebook" card: WhatsApp (Embedded Signup) and Facebook Pages + Instagram. */
export function FacebookConnect({ cfg, onDone }: { cfg: MetaConfig; onDone: (text: string) => void }) {
  const t = useT();
  const [busy, setBusy] = useState<"" | "wa" | "pages">("");
  const [error, setError] = useState("");
  const [wa, setWa] = useState<{ code: string; waba_id: string; phone_number_id: string } | null>(null);
  const [pages, setPages] = useState<{ session: string; pages: MetaPage[] } | null>(null);
  const session = useRef<{ waba_id?: string; phone_number_id?: string; event?: string }>({});

  useEffect(() => {
    // Embedded Signup tells us which WhatsApp account and number were picked through a message from facebook.com
    const onMessage = (e: MessageEvent) => {
      if (!/(^|\.)facebook\.com$/.test(new URL(e.origin).hostname)) return;
      try {
        const data = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
        if (data?.type === "WA_EMBEDDED_SIGNUP") session.current = { ...(data.data || {}), event: data.event };
      } catch { /* other facebook.com messages */ }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  async function connectWhatsApp() {
    setBusy("wa"); setError(""); session.current = {};
    try {
      const sdk = await loadSdk(cfg.app_id, cfg.graph_version);
      const code = await fbLogin(sdk, {
        config_id: cfg.whatsapp.config_id, response_type: "code", override_default_response_type: true,
        extras: { setup: {}, featureType: "", sessionInfoVersion: "3" },
      });
      for (let i = 0; i < 30 && !session.current.phone_number_id; i++) await new Promise((r) => setTimeout(r, 100));
      if (session.current.event === "CANCEL") throw new Error("The WhatsApp setup was closed before finishing. Please try again and finish every step.");
      // If the popup didn't tell us the number, the server finds it from what was shared
      const { waba_id = "", phone_number_id = "" } = session.current;
      setWa({ code, waba_id, phone_number_id });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't connect");
    } finally { setBusy(""); }
  }

  async function connectPages() {
    setBusy("pages"); setError("");
    try {
      const sdk = await loadSdk(cfg.app_id, cfg.graph_version);
      // Access token (not a code): a code from the JS SDK popup can't be exchanged server-side
      // ("redirect_uri is not identical"). The server verifies the token belongs to our app.
      const accessToken = await fbLogin(sdk, { config_id: cfg.pages.config_id }, "accessToken");
      setPages(await Api.metaPages(accessToken));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't connect");
    } finally { setBusy(""); }
  }

  return (
    <div className="card overflow-hidden border-[#1877F2]/30">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#1877F2] text-white"><SiFacebook size={24} /></span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{t("Connect with Facebook")} <span className="ml-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-700">{t("Easiest")}</span></p>
          <p className="text-sm text-slate-600">{t("Log in with Facebook and pick your WhatsApp number, Pages and Instagram accounts. No tokens to copy.")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {cfg.whatsapp.enabled && (
            <button className="btn-secondary" onClick={connectWhatsApp} disabled={!!busy}>
              {busy === "wa" ? <LoaderCircle size={16} className="animate-spin" /> : <ProviderIcon provider="whatsapp" size="xs" />} WhatsApp
            </button>
          )}
          {cfg.pages.enabled && (
            <button className="btn bg-[#1877F2] text-white hover:bg-[#166fe0]" onClick={connectPages} disabled={!!busy}>
              {busy === "pages" ? <LoaderCircle size={16} className="animate-spin" /> : <SiFacebook size={15} />} {t("Pages & Instagram")}
            </button>
          )}
        </div>
      </div>
      {error && <p className="border-t border-red-100 bg-red-50 px-5 py-2 text-sm text-red-700">{t(error)}</p>}
      {wa && <WhatsAppPin data={wa} onClose={() => setWa(null)} onDone={(text) => { setWa(null); onDone(text); }} />}
      {pages && <PagePicker data={pages} onClose={() => setPages(null)} onDone={(text) => { setPages(null); onDone(text); }} />}
    </div>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const t = useT();
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 sm:items-center sm:p-4" onClick={onClose}>
      <div className="scroll-thin max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label={t("Close")}><X size={20} /></button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

function WhatsAppPin({ data, onClose, onDone }: {
  data: { code: string; waba_id: string; phone_number_id: string }; onClose: () => void; onDone: (text: string) => void;
}) {
  const t = useT();
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function finish(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const ch = await Api.metaWhatsApp({ ...data, pin });
      onDone(t("{name} is connected. WhatsApp messages will arrive in your inbox.", { name: ch.name }));
    } catch (err) { setError(err instanceof Error ? err.message : "Couldn't connect"); }
    finally { setBusy(false); }
  }
  return (
    <Modal title={t("Finish connecting WhatsApp")} onClose={onClose}>
      <form onSubmit={finish} className="space-y-3 text-sm">
        <p className="text-slate-600">{t("Choose a 6-digit PIN for WhatsApp two-step verification. If this number already has a PIN, enter that one. Keep it somewhere safe.")}</p>
        <input className="input text-center text-lg tracking-[0.4em]" inputMode="numeric" maxLength={6} placeholder="••••••" value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} />
        <p className="text-xs text-slate-500">{t("Moving a number from the WhatsApp Business app? Leave it empty and continue.")}</p>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{t(error)}</p>}
        <button className="btn-primary w-full" disabled={busy || (pin.length > 0 && pin.length !== 6)}>
          {busy && <LoaderCircle size={16} className="animate-spin" />} {t("Connect WhatsApp")}
        </button>
      </form>
    </Modal>
  );
}

function PagePicker({ data, onClose, onDone }: { data: { session: string; pages: MetaPage[] }; onClose: () => void; onDone: (text: string) => void }) {
  const t = useT();
  const [pages, setPages] = useState<string[]>(data.pages.filter((p) => !p.connected).map((p) => p.id));
  const [ig, setIg] = useState<string[]>(data.pages.flatMap((p) => (p.instagram && !p.instagram.connected ? [p.instagram.id] : [])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const toggle = (list: string[], set: (v: string[]) => void, id: string) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  async function connect() {
    setBusy(true); setError("");
    try {
      const made = await Api.metaPagesConnect({ session: data.session, pages, instagram: ig });
      const failed = made.filter((c) => c.status === "error");
      onDone(failed.length
        ? t("Connected {n}; {errors}", { n: made.length - failed.length, errors: failed.map((c) => `${c.name}: ${c.last_error}`).join(" ") })
        : t("Connected {names}.", { names: made.map((c) => c.name).join(", ") }));
    } catch (err) { setError(err instanceof Error ? err.message : "Couldn't connect"); }
    finally { setBusy(false); }
  }
  return (
    <Modal title={t("Choose what to connect")} onClose={onClose}>
      <div className="space-y-2 text-sm">
        {data.pages.map((p) => (
          <div key={p.id} className="rounded-lg border border-slate-200 p-3">
            <label className="flex items-center gap-3">
              <input type="checkbox" className="accent-brand-600" checked={pages.includes(p.id)} onChange={() => toggle(pages, setPages, p.id)} />
              {p.picture
                // eslint-disable-next-line @next/next/no-img-element
                ? <img src={p.picture} alt="" className="h-8 w-8 rounded-full" /> : <ProviderIcon provider="messenger" size="sm" />}
              <span className="min-w-0 flex-1"><span className="block truncate font-medium">{p.name}</span><span className="text-xs text-slate-500">{t("Messenger + Page comments")}</span></span>
              {p.connected && <span className="flex items-center gap-1 text-xs text-emerald-700"><CircleCheck size={13} /> {t("connected")}</span>}
            </label>
            {p.instagram && (
              <label className="mt-2 flex items-center gap-3 border-t border-slate-100 pl-7 pt-2">
                <input type="checkbox" className="accent-brand-600" checked={ig.includes(p.instagram.id)} onChange={() => toggle(ig, setIg, p.instagram!.id)} />
                <ProviderIcon provider="instagram" size="xs" />
                <span className="flex-1">@{p.instagram.username} <span className="text-xs text-slate-500">{t("DMs + comments")}</span></span>
                {p.instagram.connected && <span className="flex items-center gap-1 text-xs text-emerald-700"><CircleCheck size={13} /> {t("connected")}</span>}
              </label>
            )}
          </div>
        ))}
        <p className="text-xs text-slate-500">{t("Don't see an Instagram account? Link it to its Facebook Page in Instagram settings, then connect again.")}</p>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{t(error)}</p>}
        <button className="btn-primary w-full" disabled={busy || (!pages.length && !ig.length)} onClick={connect}>
          {busy && <LoaderCircle size={16} className="animate-spin" />}{" "}
          {pages.length + ig.length === 0 ? t("Connect accounts") : pages.length + ig.length === 1 ? t("Connect 1 account") : t("Connect {n} accounts", { n: pages.length + ig.length })}
        </button>
      </div>
    </Modal>
  );
}
