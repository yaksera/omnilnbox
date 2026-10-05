"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, LogOut, MonitorSmartphone } from "lucide-react";
import { Api } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** Log out of this device, or of every device at once (e.g. after losing a phone). */
export default function SessionsSection() {
  const t = useT();
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState<"" | "one" | "all">("");
  const [error, setError] = useState("");

  async function logout(all: boolean) {
    setBusy(all ? "all" : "one"); setError("");
    try {
      if (all) await Api.logoutAll();
      await Api.logout();
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn’t log out"));
      setBusy("");
    }
  }

  return (
    <section className="card p-5" id="sessions">
      <h2 className="flex items-center gap-2 font-semibold"><MonitorSmartphone size={18} /> {t("Sessions")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t("Log out here, or everywhere you’re signed in: other browsers, phones and installed apps.")}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" className="btn-secondary" disabled={!!busy} onClick={() => logout(false)}>
          {busy === "one" ? <LoaderCircle className="animate-spin" size={15} /> : <LogOut size={15} />} {t("Log out")}
        </button>
        {confirm ? (
          <span className="flex flex-wrap items-center gap-2 rounded-lg bg-red-50 px-3 py-1.5 text-sm text-red-800">
            {t("Sign out on every device, including this one?")}
            <button type="button" className="btn-primary bg-red-600 px-3 py-1 hover:bg-red-700" disabled={!!busy} onClick={() => logout(true)}>
              {busy === "all" && <LoaderCircle className="animate-spin" size={14} />} {t("Yes, log out everywhere")}
            </button>
            <button type="button" className="px-2 py-1 text-slate-600 hover:text-slate-900" onClick={() => setConfirm(false)}>{t("Cancel")}</button>
          </span>
        ) : (
          <button type="button" className="btn-secondary text-red-600" disabled={!!busy} onClick={() => setConfirm(true)}>{t("Log out of all devices")}</button>
        )}
      </div>
      <p className="mt-3 text-xs text-slate-500">{t("Lost a phone or used a shared computer? Log out of all devices, then change your password.")}</p>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  );
}
