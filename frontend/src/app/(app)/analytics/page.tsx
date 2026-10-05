"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { Download, LoaderCircle } from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import type { Analytics } from "@/lib/types";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { UpgradeHint, useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

// Validated categorical pair (dataviz palette slots 1 & 2): identity is also given by legend + tooltip text.
const C_IN = "#2a78d6";
const C_OUT = "#eb6834";

function Tile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  const t = useT();
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t(label)}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
      {sub && <p className="text-xs text-slate-500">{t(sub)}</p>}
    </div>
  );
}

function VolumeChart({ series }: { series: Analytics["series"] }) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);
  const W = 720, H = 220, PAD_L = 36, PAD_B = 24, PAD_T = 8;
  const max = Math.max(4, ...series.map((d) => Math.max(d.in, d.out)));
  const step = Math.pow(10, Math.floor(Math.log10(max)));
  const top = Math.ceil(max / step) * step;
  const ticks = [0, top / 2, top];
  const slot = (W - PAD_L) / series.length;
  const barW = Math.max(2, Math.min(14, (slot - 6) / 2));
  const y = (v: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - v / top);
  const every = Math.ceil(series.length / 8);
  const d = hover !== null ? series[hover] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("Messages per day, incoming and outgoing")}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD_L} x2={W} y1={y(tick)} y2={y(tick)} stroke="#e2e8f0" strokeWidth={1} />
            <text x={PAD_L - 6} y={y(tick) + 4} textAnchor="end" fontSize={10} fill="#64748b">{tick}</text>
          </g>
        ))}
        {series.map((row, i) => {
          const x0 = PAD_L + i * slot + (slot - (barW * 2 + 2)) / 2;
          return (
            <g key={row.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={PAD_L + i * slot} y={PAD_T} width={slot} height={H - PAD_T - PAD_B} fill={hover === i ? "#f1f5f9" : "transparent"} />
              {row.in > 0 && <rect x={x0} y={y(row.in)} width={barW} height={y(0) - y(row.in)} rx={Math.min(3, barW / 2)} fill={C_IN} />}
              {row.out > 0 && <rect x={x0 + barW + 2} y={y(row.out)} width={barW} height={y(0) - y(row.out)} rx={Math.min(3, barW / 2)} fill={C_OUT} />}
              {i % every === 0 && (
                <text x={PAD_L + i * slot + slot / 2} y={H - 6} textAnchor="middle" fontSize={10} fill="#64748b">
                  {new Date(row.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD_L} x2={W} y1={y(0)} y2={y(0)} stroke="#94a3b8" strokeWidth={1} />
      </svg>
      {d && (
        <div className="pointer-events-none absolute right-2 top-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
          <p className="font-semibold text-slate-900">{new Date(d.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</p>
          <p className="mt-1 flex items-center gap-2 text-slate-700"><span className="h-2 w-2 rounded-sm" style={{ background: C_IN }} /> {t("Incoming")} <b className="ml-auto pl-3">{d.in}</b></p>
          <p className="flex items-center gap-2 text-slate-700"><span className="h-2 w-2 rounded-sm" style={{ background: C_OUT }} /> {t("Replies")} <b className="ml-auto pl-3">{d.out}</b></p>
        </div>
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  const { hasFeature } = useMe();
  const t = useT();
  const [days, setDays] = useState(14);
  const [data, setData] = useState<Analytics | null>(null);
  const [locked, setLocked] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [exportError, setExportError] = useState("");

  useEffect(() => {
    setData(null);
    Api.analytics(days).then(setData).catch((e) => { if (e instanceof ApiError && e.status === 402) setLocked(true); });
  }, [days]);

  if (locked || !hasFeature("analytics")) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16">
        <UpgradeHint feature={t("Analytics")}>{t("See message volume, first response time and replies per agent on Pro and Business.")}</UpgradeHint>
      </div>
    );
  }

  const maxChannel = Math.max(1, ...(data?.by_channel.map((c) => c.incoming + c.outgoing) ?? [1]));
  const maxAgent = Math.max(1, ...(data?.by_agent.map((a) => a.replies) ?? [1]));

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{t("Analytics")}</h1>
            <p className="mt-1 text-sm text-slate-600">{t("Team performance across all channels.")}</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-lg bg-slate-100 p-1 text-sm">
              {[7, 14, 30, 90].map((d) => (
                <button key={d} onClick={() => setDays(d)} className={clsx("rounded-md px-3 py-1.5 font-medium", days === d ? "bg-white shadow-sm" : "text-slate-600")}>{t("{n}d", { n: d })}</button>
              ))}
            </div>
            <button className="btn-secondary" title={hasFeature("csv_export") ? t("Download CSV") : t("CSV export is on the Business plan")}
              disabled={!hasFeature("csv_export")}
              onClick={() => Api.downloadExport(days).catch((e) => setExportError(e instanceof Error ? e.message : "Export failed"))}>
              <Download size={16} /> {t("Export")}
            </button>
          </div>
        </div>
        {exportError && <p className="text-sm text-red-600">{t(exportError)}</p>}

        {!data ? (
          <div className="flex justify-center py-16 text-slate-400"><LoaderCircle className="animate-spin" /></div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
              <Tile label="New conversations" value={data.totals.new_conversations} />
              <Tile label="Messages received" value={data.totals.incoming} />
              <Tile label="Replies sent" value={data.totals.outgoing} />
              <Tile label="Closed" value={data.totals.closed} />
              <Tile label="Avg. first response" value={data.totals.avg_first_response_minutes === null ? "—" : data.totals.avg_first_response_minutes < 60
                ? t("{n} min", { n: data.totals.avg_first_response_minutes }) : t("{n} h", { n: (data.totals.avg_first_response_minutes / 60).toFixed(1) })} sub="time to first reply" />
            </div>

            {(data.sla || data.csat) && (
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="card p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("Replied within target")}</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{data.sla?.met_pct === null || data.sla?.met_pct === undefined ? "—" : `${data.sla.met_pct}%`}</p>
                  <p className="text-xs text-slate-500">{data.sla?.target_minutes ? t("Target: first reply within {min} min · {n} conversations", { min: data.sla.target_minutes, n: data.sla.measured }) : t("No target set (Settings → Service quality)")}</p>
                </div>
                <div className="card p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("Customer satisfaction")}</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{data.csat?.avg ? `${data.csat.avg} / 5` : "—"}</p>
                  <p className="text-xs text-slate-500">{data.csat?.responses ? t("{pct}% happy (4-5) · {n} ratings", { pct: data.csat.happy_pct ?? "", n: data.csat.responses }) : data.csat?.enabled ? t("No ratings yet in this period") : t("Turn on surveys in Settings → Service quality")}</p>
                </div>
                <div className="card p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("Latest feedback")}</p>
                  {data.csat?.recent.length ? (
                    <ul className="mt-2 space-y-1 text-sm">{data.csat.recent.slice(0, 3).map((r, i) => (
                      <li key={i} className="truncate"><span className="text-amber-500">{"★".repeat(r.score)}<span className="text-slate-200">{"★".repeat(5 - r.score)}</span></span> <span className="text-slate-600">{r.contact}{r.comment && `: “${r.comment}”`}</span></li>
                    ))}</ul>
                  ) : <p className="mt-2 text-sm text-slate-500">—</p>}
                </div>
              </div>
            )}
            {!!data.csat?.by_agent.length && (
              <div className="card p-5">
                <h2 className="font-semibold">{t("Satisfaction by agent")}</h2>
                <ul className="mt-3 divide-y divide-slate-100 text-sm">
                  {data.csat.by_agent.map((a) => <li key={a.name} className="flex justify-between py-2"><span className="font-medium">{a.name}</span><span><span className="text-amber-500">★</span> {a.avg} <span className="text-slate-400">({a.responses})</span></span></li>)}
                </ul>
              </div>
            )}

            <div className="card p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-semibold">{t("Messages per day")}</h2>
                <div className="flex items-center gap-4 text-xs text-slate-600">
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: C_IN }} /> {t("Incoming")}</span>
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: C_OUT }} /> {t("Replies")}</span>
                  <button className="text-brand-600 hover:underline" onClick={() => setShowTable(!showTable)}>{showTable ? t("Hide table") : t("Show table")}</button>
                </div>
              </div>
              <div className="mt-4"><VolumeChart series={data.series} /></div>
              {showTable && (
                <div className="mt-4 max-h-64 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">{t("Date")}</th><th>{t("Incoming")}</th><th>{t("Replies")}</th></tr></thead>
                    <tbody>{data.series.map((r) => <tr key={r.date} className="border-t border-slate-100"><td className="py-1">{r.date}</td><td>{r.in}</td><td>{r.out}</td></tr>)}</tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <div className="card p-5">
                <h2 className="font-semibold">{t("By channel")}</h2>
                {data.by_channel.length === 0 ? <p className="mt-4 text-sm text-slate-500">{t("No messages in this period.")}</p> : (
                  <ul className="mt-4 space-y-3">
                    {data.by_channel.map((c) => (
                      <li key={c.provider} className="flex items-center gap-3">
                        <ProviderIcon provider={c.provider} size="sm" />
                        <div className="min-w-0 flex-1">
                          <div className="flex justify-between text-sm"><span className="font-medium text-slate-800">{providerUI(c.provider).label}</span>
                            <span className="text-slate-600">{t("{in} in · {out} out", { in: c.incoming, out: c.outgoing })}</span></div>
                          <div className="mt-1 h-2 rounded-full bg-slate-100">
                            <div className="h-full rounded-full bg-slate-700" style={{ width: `${((c.incoming + c.outgoing) / maxChannel) * 100}%` }} />
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="card p-5">
                <h2 className="font-semibold">{t("Replies by agent")}</h2>
                {data.by_agent.length === 0 ? <p className="mt-4 text-sm text-slate-500">{t("No replies in this period.")}</p> : (
                  <ul className="mt-4 space-y-3">
                    {data.by_agent.map((a) => (
                      <li key={a.name}>
                        <div className="flex justify-between text-sm"><span className="font-medium text-slate-800">{a.name}</span><span className="text-slate-600">{a.replies}</span></div>
                        <div className="mt-1 h-2 rounded-full bg-slate-100"><div className="h-full rounded-full bg-brand-600" style={{ width: `${(a.replies / maxAgent) * 100}%` }} /></div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
