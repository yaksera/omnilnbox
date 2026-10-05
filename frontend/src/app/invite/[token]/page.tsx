"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle } from "lucide-react";
import Logo from "@/components/Logo";
import { Api, auth } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/money";
import { useT } from "@/lib/i18n";

export default function AcceptInvite({ params }: { params: Promise<{ token: string }> }) {
  const t = useT();
  const { token } = use(params);
  const router = useRouter();
  const [info, setInfo] = useState<{ workspace: string; email: string; role: string; user_exists: boolean } | null>(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    Api.inviteInfo(token).then(setInfo).catch((e) => { setLoadFailed(true); setError(e instanceof Error ? e.message : ""); });
  }, [token]);

  async function accept(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await Api.acceptInvite(token, { name, password });
      auth.clear();
      auth.set(r);
      auth.setWorkspace(r.workspace_id);
      router.push("/inbox");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn't accept the invitation"));
      setBusy(false);
    }
  }

  const invited = info ? t("You've been invited as {role} with {email}.", { email: info.email }).split("{role}") : [];

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <Logo className="mb-8 justify-center" />
        <div className="card p-6">
          {!info && !loadFailed && <div className="flex justify-center py-6 text-slate-400"><LoaderCircle className="animate-spin" /></div>}
          {!info && loadFailed && <p className="text-sm text-red-700">{error || t("Invalid invitation")}</p>}
          {info && (
            <form onSubmit={accept} className="space-y-4">
              <div>
                <h1 className="text-lg font-semibold">{t("Join {workspace}", { workspace: info.workspace })}</h1>
                <p className="mt-1 text-sm text-slate-600">{invited[0]}<b>{t(ROLE_LABELS[info.role] ?? info.role)}</b>{invited[1]}</p>
              </div>
              {!info.user_exists && (
                <label className="block text-sm"><span className="mb-1 block font-medium text-slate-700">{t("Your name")}</span>
                  <input className="input" required value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
              )}
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">{info.user_exists ? t("Your OmniInbox password") : t("Choose a password")}</span>
                <input className="input" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete={info.user_exists ? "current-password" : "new-password"} />
              </label>
              {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
              <button className="btn-primary w-full" disabled={busy}>{busy && <LoaderCircle className="animate-spin" size={16} />} {t("Accept invitation")}</button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
