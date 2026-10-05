"use client";

import { useEffect, useState } from "react";
import { Download, Smartphone } from "lucide-react";
import { canPromptInstall, isInstalled, isIOS, promptInstall } from "@/lib/notifications";
import { useT } from "@/lib/i18n";

/** Render a translated sentence, swapping {key} placeholders for bold labels. */
function rich(text: string, parts: Record<string, string>) {
  return text.split(/(\{\w+\})/).map((p, i) => {
    const m = /^\{(\w+)\}$/.exec(p);
    return m && m[1] in parts ? <b key={i}>{parts[m[1]]}</b> : p;
  });
}

export default function InstallCard() {
  const t = useT();
  const [state, setState] = useState<"installed" | "prompt" | "ios" | "manual">("manual");
  useEffect(() => {
    const check = () => setState(isInstalled() ? "installed" : canPromptInstall() ? "prompt" : isIOS() ? "ios" : "manual");
    check();
    const timer = setTimeout(check, 1500); // the browser fires its install event shortly after load
    return () => clearTimeout(timer);
  }, []);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-4">
      <Download size={20} className="text-brand-600" />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium">{t("Install OmniInbox as an app")}</p>
        {state === "installed" && <p className="text-xs text-emerald-700">{t("Installed. You’re using the app version.")}</p>}
        {state === "prompt" && <p className="text-xs text-slate-500">{t("Opens in its own window with an icon on your home screen / taskbar.")}</p>}
        {state === "ios" && <p className="text-xs text-slate-500">{rich(t("On iPhone/iPad: open this page in {safari} → tap {share} → {add}. Then open OmniInbox from the icon and turn on notifications below."), { safari: "Safari", share: t("Share"), add: t("Add to Home Screen") })}</p>}
        {state === "manual" && <p className="text-xs text-slate-500">{rich(t("Android (Chrome): menu ⋮ → {install}. Computer (Chrome/Edge): the install icon at the right of the address bar."), { install: t("Install app") })}</p>}
      </div>
      {state === "prompt" && <button type="button" className="btn-primary" onClick={async () => { if (await promptInstall()) setState("installed"); }}><Smartphone size={15} /> {t("Install")}</button>}
    </div>
  );
}
