"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CircleCheck, Copy, LoaderCircle, Trash, UserPlus } from "lucide-react";
import { Api } from "@/lib/api";
import type { Role, Team } from "@/lib/types";
import { avatarColor, initials } from "@/lib/format";
import { ROLE_HELP, ROLE_LABELS } from "@/lib/money";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const ROLE_BADGE: Record<Role, string> = {
  owner: "bg-violet-100 text-violet-700",
  admin: "bg-sky-100 text-sky-700",
  supervisor: "bg-amber-100 text-amber-800",
  agent: "bg-emerald-100 text-emerald-700",
};
const RANK: Record<Role, number> = { owner: 4, admin: 3, supervisor: 2, agent: 1 };

export default function TeamPage() {
  const t = useT();
  const { me, can, hasFeature } = useMe();
  const [team, setTeam] = useState<Team | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("agent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastLink, setLastLink] = useState<{ url: string; emailed: boolean; email: string } | null>(null);
  const [copied, setCopied] = useState("");

  const reload = useCallback(() => Api.team().then(setTeam), []);
  useEffect(() => { reload(); }, [reload]);

  const canManage = can("manage_team");
  const grantable: Role[] = (["admin", "supervisor", "agent"] as Role[]).filter((r) =>
    (r !== "admin" || me.role === "owner") && (r !== "supervisor" || hasFeature("supervisor_role")));

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await Api.invite(email.trim(), role);
      setLastLink({ url: r.url, emailed: r.emailed, email: r.email });
      setEmail("");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn’t send invite"));
    } finally {
      setBusy(false);
    }
  }

  function copy(url: string) {
    navigator.clipboard?.writeText(url);
    setCopied(url);
    setTimeout(() => setCopied(""), 1500);
  }

  async function act(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Action failed"));
    }
    reload();
  }

  if (!team) return <div className="flex h-full items-center justify-center text-slate-400"><LoaderCircle className="animate-spin" /></div>;
  const full = team.seats_used >= team.seat_limit;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{t("Team")}</h1>
            <p className="mt-1 text-sm text-slate-600">{t("{used} of {limit} seats used, including pending invites.", { used: team.seats_used, limit: team.seat_limit })}</p>
          </div>
          {full && me.role === "owner" && <Link href="/billing" className="btn-secondary">{t("Add seats")}</Link>}
        </div>

        {canManage && (
          <form onSubmit={invite} className="card p-5">
            <h2 className="flex items-center gap-2 font-semibold"><UserPlus size={18} /> {t("Invite a teammate")}</h2>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <input className="input" type="email" placeholder="teammate@company.com" required value={email} onChange={(e) => setEmail(e.target.value)} disabled={full} />
              <select className="input sm:w-44" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {grantable.map((r) => <option key={r} value={r}>{t(ROLE_LABELS[r])}</option>)}
              </select>
              <button className="btn-primary" disabled={busy || full}>{busy && <LoaderCircle className="animate-spin" size={16} />} {t("Send invite")}</button>
            </div>
            <p className="mt-2 text-xs text-slate-500">{t(ROLE_LABELS[role])}: {t(ROLE_HELP[role])}</p>
            {!hasFeature("supervisor_role") && <p className="mt-1 text-xs text-slate-500">{t("The Supervisor role is available on Pro and higher.")}</p>}
            {full && <p className="mt-2 text-sm text-amber-700">{t("All seats are in use.")} {me.role === "owner" ? t("Add seats or upgrade on the Billing page.") : t("Ask the owner to add seats.")}</p>}
            {lastLink && (
              <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
                <p className="flex items-center gap-2 font-medium"><CircleCheck size={16} />
                  {lastLink.emailed ? t("Invite emailed to {email}.", { email: lastLink.email }) : t("Invite created for {email}. Send them this link:", { email: lastLink.email })}</p>
                <div className="mt-2 flex items-center gap-2 rounded-md bg-white px-2 py-1.5 font-mono text-xs">
                  <span className="flex-1 truncate">{lastLink.url}</span>
                  <button type="button" onClick={() => copy(lastLink.url)} className="text-slate-500 hover:text-slate-900" aria-label={t("Copy link")}>{copied === lastLink.url ? <CircleCheck size={14} /> : <Copy size={14} />}</button>
                </div>
                <p className="mt-1 text-xs text-emerald-800">{t("The link expires in {n} days and works once.", { n: 7 })}</p>
              </div>
            )}
          </form>
        )}

        {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

        <div className="card overflow-hidden">
          <h2 className="border-b border-slate-100 px-5 py-3 font-semibold">{t("Members")}</h2>
          <ul className="divide-y divide-slate-100">
            {team.members.map((m) => {
              const manageable = canManage && m.role !== "owner" && m.id !== me.user.id && (me.role === "owner" || RANK[m.role] < RANK[me.role]);
              return (
                <li key={m.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full text-xs font-semibold text-white" style={{ background: avatarColor(m.email) }}>{initials(m.name)}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{m.name}{m.id === me.user.id && <span className="text-slate-400"> {t("(you)")}</span>}</p>
                    <p className="truncate text-xs text-slate-500">{m.email}</p>
                  </div>
                  {manageable ? (
                    <>
                      <select className="input w-36 py-1.5" value={m.role} onChange={(e) => act(() => Api.setRole(m.id, e.target.value as Role))}>
                        {Array.from(new Set([...grantable, m.role])).map((r) => <option key={r} value={r}>{t(ROLE_LABELS[r])}</option>)}
                      </select>
                      <button className="btn-ghost px-2 text-red-600 hover:bg-red-50" title={t("Remove from workspace")}
                        onClick={() => window.confirm(t("Remove {name} from {workspace}? Their conversations become unassigned.", { name: m.name, workspace: me.workspace.name })) && act(() => Api.removeMember(m.id))}>
                        <Trash size={16} />
                      </button>
                    </>
                  ) : (
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${ROLE_BADGE[m.role]}`}>{t(ROLE_LABELS[m.role])}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        {canManage && team.invites.length > 0 && (
          <div className="card overflow-hidden">
            <h2 className="border-b border-slate-100 px-5 py-3 font-semibold">{t("Pending invites")}</h2>
            <ul className="divide-y divide-slate-100">
              {team.invites.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{i.email}</p>
                    <p className="text-xs text-slate-500">{t(ROLE_LABELS[i.role])} · {t("expires {date}", { date: new Date(i.expires_at).toLocaleDateString() })}</p>
                  </div>
                  <button className="btn-secondary px-2.5 py-1.5" onClick={() => copy(i.url)}>{copied === i.url ? <CircleCheck size={14} /> : <Copy size={14} />} {t("Copy link")}</button>
                  <button className="btn-ghost px-2.5 py-1.5 text-red-600 hover:bg-red-50" onClick={() => act(() => Api.revokeInvite(i.id))}>{t("Revoke")}</button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="card p-5">
          <h2 className="font-semibold">{t("What each role can do")}</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {(["owner", "admin", "supervisor", "agent"] as Role[]).map((r) => (
              <div key={r} className="rounded-lg border border-slate-200 p-3">
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${ROLE_BADGE[r]}`}>{t(ROLE_LABELS[r])}</span>
                <p className="mt-2 text-sm text-slate-600">{t(ROLE_HELP[r])}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
