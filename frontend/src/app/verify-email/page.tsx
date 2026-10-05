"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import { Api } from "@/lib/api";
import { AuthShell } from "@/components/AuthForm";
import { useT } from "@/lib/i18n";

export default function VerifyEmailPage() {
  const t = useT();
  const [state, setState] = useState<{ status: "loading" | "ok" | "error"; text: string }>({ status: "loading", text: "" });

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token") || "";
    Api.verifyEmail(token)
      .then((r) => setState({ status: "ok", text: r.email }))
      .catch((err) => setState({ status: "error", text: err instanceof Error ? err.message : "" }));
  }, []);

  const confirmed = t("{email} is confirmed. Thanks!").split("{email}");

  return (
    <AuthShell>
      <div className="card space-y-3 p-6 text-center">
        {state.status === "loading" && <LoaderCircle className="mx-auto animate-spin text-slate-400" size={32} />}
        {state.status === "ok" && (
          <>
            <CircleCheck className="mx-auto text-emerald-600" size={36} />
            <h1 className="text-lg font-semibold">{t("Email confirmed")}</h1>
            <p className="text-sm text-slate-600">{confirmed[0]}<b>{state.text}</b>{confirmed[1]}</p>
            <Link href="/inbox" className="btn-primary w-full">{t("Go to OmniInbox")}</Link>
          </>
        )}
        {state.status === "error" && (
          <>
            <CircleAlert className="mx-auto text-red-500" size={36} />
            <h1 className="text-lg font-semibold">{t("Link not valid")}</h1>
            <p className="text-sm text-slate-600">{state.text || t("Invalid link")} {t("Log in and click \"Resend\" on the yellow banner to get a new link.")}</p>
            <Link href="/login" className="btn-secondary w-full">{t("Log in")}</Link>
          </>
        )}
      </div>
    </AuthShell>
  );
}
