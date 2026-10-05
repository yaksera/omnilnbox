"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, History, LoaderCircle } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import type { AuditRow } from "@/lib/types";
import { UpgradeHint } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

const FILTERS = [["", "Everything"], ["auth.", "Logins & security"], ["team.", "Team"], ["channel.", "Channels"], ["billing.", "Billing"],
  ["automation.", "Automations"], ["ai.", "AI"], ["order.", "Orders"], ["api_key.", "API keys"]] as const;

export default function ActivityPage() {
  const t = useT();
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [filter, setFilter] = useState("");
  const [state, setState] = useState<"ok" | "upgrade" | "forbidden">("ok");

  useEffect(() => {
    Api.auditLog(page, filter)
      .then((r) => { setRows((prev) => (page === 1 ? r.results : [...(prev ?? []), ...r.results])); setMore(r.has_more); })
      .catch((err) => setState(err instanceof ApiError && err.status === 402 ? "upgrade" : "forbidden"));
  }, [page, filter]);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-8 sm:px-6">
        <Link href="/settings" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={16} /> {t("Settings")}</Link>
        <h1 className="flex items-center gap-2 text-2xl font-bold"><History size={22} /> {t("Activity log")}</h1>
        <p className="text-sm text-slate-600">{t("Who did what in this workspace: logins, team changes, channels, billing and automations.")}</p>
        {state === "upgrade" ? <UpgradeHint feature={t("The activity log")}>{t("See a full audit trail of your team on the Business plan.")}</UpgradeHint>
          : state === "forbidden" ? <p className="text-sm text-slate-500">{t("Only the owner and admins can see the activity log.")}</p> : (
          <>
            <div className="flex flex-wrap gap-1">
              {FILTERS.map(([v, l]) => (
                <button key={v} type="button" onClick={() => { setFilter(v); setPage(1); setRows(null); }}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${filter === v ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{t(l)}</button>
              ))}
            </div>
            {rows === null ? <LoaderCircle className="animate-spin text-slate-400" /> : rows.length === 0 ? <p className="card p-6 text-center text-sm text-slate-500">{t("Nothing here yet.")}</p> : (
              <div className="card overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                    <tr><th className="px-4 py-2">{t("When")}</th><th className="px-4 py-2">{t("Who")}</th><th className="px-4 py-2">{t("What")}</th><th className="px-4 py-2">{t("Details")}</th><th className="px-4 py-2">IP</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rows.map((r) => (
                      <tr key={r.id} className={r.action === "auth.login_failed" ? "bg-red-50/50" : ""}>
                        <td className="whitespace-nowrap px-4 py-2 text-slate-500">{new Date(r.created_at).toLocaleString()}</td>
                        <td className="px-4 py-2">{r.actor || "—"}</td>
                        <td className="px-4 py-2 font-medium">{r.label}</td>
                        <td className="max-w-xs truncate px-4 py-2 text-slate-600" title={JSON.stringify(r.meta)}>{r.target}</td>
                        <td className="px-4 py-2 font-mono text-xs text-slate-400">{r.ip ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {more && <button type="button" className="btn-secondary" onClick={() => setPage(page + 1)}>{t("Load more")}</button>}
          </>
        )}
      </div>
    </div>
  );
}
