"use client";

import { useEffect, useState } from "react";
import { Bell, BellOff, LoaderCircle, Send, Smartphone } from "lucide-react";
import { Api } from "@/lib/api";
import type { NotificationPrefs } from "@/lib/types";
import { useMe } from "@/components/AppShell";
import InstallCard from "./InstallCard";
import { useT } from "@/lib/i18n";
import { chime, disablePush, enablePush, localPrefs, pushEnabledHere, pushSupported, saveLocalPrefs } from "@/lib/notifications";

const ALERT_OPTIONS = [[0, "Off"], [15, "15 minutes"], [30, "30 minutes"], [60, "1 hour"], [120, "2 hours"], [240, "4 hours"]] as const;

function Toggle({ checked, onChange, label, help }: { checked: boolean; onChange: (v: boolean) => void; label: string; help: string }) {
  return (
    <label className="flex items-start gap-3">
      <input type="checkbox" className="mt-1 h-4 w-4 accent-brand-600" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span><span className="block text-sm font-medium">{label}</span><span className="block text-xs text-slate-500">{help}</span></span>
    </label>
  );
}

export default function NotificationsSection() {
  const t = useT();
  const { me, can, reloadMe } = useMe();
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [local, setLocal] = useState({ sound: true, desktop: true });
  const [here, setHere] = useState(false);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    Api.notificationPrefs().then(setPrefs).catch(() => undefined);
    setLocal(localPrefs());
    pushEnabledHere().then(setHere);
  }, []);

  const setLocalPref = (k: "sound" | "desktop", v: boolean) => { const next = { ...local, [k]: v }; setLocal(next); saveLocalPrefs(next); if (k === "sound" && v) chime(); };

  async function togglePush() {
    setBusy("push"); setNote("");
    try {
      if (here) { await disablePush(); setHere(false); setNote(t("Notifications turned off on this device.")); }
      else {
        const r = await enablePush();
        if (r === "on") { setHere(true); setNote(t("Done! You’ll get notified on this device, even when OmniInbox is closed.")); }
        else if (r === "denied") setNote(t("Your browser blocked notifications. Click the lock icon in the address bar → Notifications → Allow, then try again."));
        else setNote(t("This browser can’t receive push notifications. On iPhone/iPad: open OmniInbox in Safari → Share → Add to Home Screen, then turn this on from the app."));
      }
      setPrefs(await Api.notificationPrefs());
    } finally { setBusy(""); }
  }

  return (
    <section className="card p-5" id="notifications">
      <h2 className="flex items-center gap-2 font-semibold"><Bell size={18} /> {t("Notifications")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t("Never miss a customer: get notified on your phone and computer when a new message arrives.")}</p>

      <div className="mt-4"><InstallCard /></div>
      <div className="mt-4 rounded-lg border border-slate-200 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <Smartphone size={20} className="text-brand-600" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{t("Push notifications on this device")} {here && <span className="ml-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">{t("On")}</span>}</p>
            <p className="text-xs text-slate-500">{t("Works when OmniInbox is closed. Turn it on separately on each phone and computer you use.")} {prefs ? t(prefs.push_devices === 1 ? "{n} device on your account." : "{n} devices on your account.", { n: prefs.push_devices }) : ""}</p>
          </div>
          <button type="button" className={here ? "btn-secondary" : "btn-primary"} disabled={busy === "push" || (!pushSupported() && !here)} onClick={togglePush}>
            {busy === "push" ? <LoaderCircle className="animate-spin" size={15} /> : here ? <BellOff size={15} /> : <Bell size={15} />} {here ? t("Turn off") : t("Turn on")}
          </button>
          {here && (
            <button type="button" className="btn-ghost" disabled={busy === "test"} onClick={async () => { setBusy("test"); await Api.pushTest().catch(() => undefined); setBusy(""); setNote(t("Test sent. It should appear in a few seconds.")); }}>
              <Send size={14} /> {t("Send a test")}
            </button>
          )}
        </div>
        {note && <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">{note}</p>}
      </div>

      <div className="mt-4 space-y-3">
        <Toggle checked={local.sound} onChange={(v) => setLocalPref("sound", v)} label={t("Play a sound for new messages")} help={t("While OmniInbox is open in this browser.")} />
        <Toggle checked={local.desktop} onChange={(v) => setLocalPref("desktop", v)} label={t("Show a desktop alert when OmniInbox is in the background")} help={t("Uses your browser’s notification permission.")} />
        {prefs && (
          <Toggle checked={prefs.email_unanswered} label={t("Email me when customers are waiting")}
            help={prefs.unanswered_alert_minutes
              ? t("Sent when a customer waits {n} minutes without a reply. Goes to the assigned agent, or to supervisors and admins for unassigned chats.", { n: prefs.unanswered_alert_minutes })
              : t("Alerts for waiting customers are off for this workspace. When on, they go to the assigned agent, or to supervisors and admins for unassigned chats.")}
            onChange={async (v) => setPrefs(await Api.saveNotificationPrefs({ email_unanswered: v }))} />
        )}
      </div>

      {can("manage_settings") && (
        <label className="mt-5 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4 text-sm">
          <span className="font-medium">{t("Workspace: alert the team when a customer waits")}</span>
          <select className="input w-40" value={me.workspace.unanswered_alert_minutes}
            onChange={async (e) => { await Api.updateWorkspace({ unanswered_alert_minutes: Number(e.target.value) }); await reloadMe(); setPrefs(await Api.notificationPrefs()); }}>
            {ALERT_OPTIONS.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
          </select>
        </label>
      )}
    </section>
  );
}
