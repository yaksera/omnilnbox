"use client";

import { useState } from "react";
import clsx from "clsx";
import { CalendarClock, ExternalLink, LoaderCircle, Pencil, RotateCcw, Trash2 } from "lucide-react";
import { Api } from "@/lib/api";
import type { SocialPost } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";

export const POST_STATUS: Record<SocialPost["status"], { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "bg-slate-100 text-slate-700" },
  scheduled: { label: "Scheduled", cls: "bg-sky-50 text-sky-700" },
  publishing: { label: "Publishing…", cls: "bg-amber-50 text-amber-700" },
  published: { label: "Published", cls: "bg-emerald-50 text-emerald-700" },
  partial: { label: "Partly failed", cls: "bg-orange-50 text-orange-700" },
  failed: { label: "Failed", cls: "bg-red-50 text-red-700" },
};

const TARGET_DOT = { pending: "bg-slate-300", publishing: "bg-amber-400 animate-pulse", published: "bg-emerald-500", failed: "bg-red-500" };

export default function PostsList({ posts, onEdit, onChanged }: {
  posts: SocialPost[]; onEdit: (p: SocialPost) => void; onChanged: () => void;
}) {
  const t = useT();
  const { can } = useMe();
  const [busy, setBusy] = useState("");
  const [filter, setFilter] = useState<"all" | SocialPost["status"]>("all");
  const shown = filter === "all" ? posts : posts.filter((p) => p.status === filter || (filter === "failed" && p.status === "partial"));

  async function act(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    try { await fn(); onChanged(); } catch (err) { window.alert(err instanceof Error ? err.message : t("Something went wrong")); } finally { setBusy(""); }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1">
        {(["all", "scheduled", "draft", "published", "failed"] as const).map((f) => (
          <button key={f} type="button" onClick={() => setFilter(f)}
            className={clsx("rounded-full px-3 py-1 text-xs font-medium", filter === f ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}>
            {f === "all" ? t("All") : t(POST_STATUS[f].label)}
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="card p-8 text-center text-sm text-slate-500">{t("No posts here yet.")}</p>
      ) : (
        <ul className="space-y-3">
          {shown.map((p) => {
            const st = POST_STATUS[p.status];
            const editable = p.status === "draft" || p.status === "scheduled";
            const retryable = p.status === "failed" || p.status === "partial";
            return (
              <li key={p.id} className="card flex gap-4 p-4">
                <div className="h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-slate-100">
                  {p.media && (p.media.kind === "image"
                    // eslint-disable-next-line @next/next/no-img-element
                    ? <img src={p.media.preview_url} alt="" className="h-full w-full object-cover" />
                    : <video src={p.media.preview_url} className="h-full w-full object-cover" muted />)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className={clsx("rounded-full px-2 py-0.5 font-medium", st.cls)}>{t(st.label)}</span>
                    {p.status === "scheduled" && p.scheduled_at && (
                      <span className="inline-flex items-center gap-1 text-slate-600"><CalendarClock size={13} /> {new Date(p.scheduled_at).toLocaleString()}</span>
                    )}
                    {p.published_at && <span className="text-slate-500">{t("Published {when}", { when: new Date(p.published_at).toLocaleString() })}</span>}
                    {p.status === "draft" && <span className="text-slate-500">{t("Saved {when}", { when: new Date(p.created_at).toLocaleDateString() })}</span>}
                    {p.created_by && <span className="text-slate-400">· {t("by {name}", { name: p.created_by })}</span>}
                  </div>
                  <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-sm text-slate-800">{p.caption || <span className="text-slate-400">{t("(no caption)")}</span>}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {p.targets.map((x) => (
                      <span key={x.account.id} title={x.error || x.options.note || ""}
                        className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-slate-200 py-0.5 pl-0.5 pr-2 text-xs">
                        <ProviderIcon provider={x.account.platform} size="xs" className="rounded-full" />
                        <span className="max-w-[140px] truncate">{x.account.name}</span>
                        <span className={clsx("h-1.5 w-1.5 rounded-full", TARGET_DOT[x.status])} />
                        {x.url && <a href={x.url} target="_blank" rel="noreferrer noopener" className="text-brand-700 hover:underline" aria-label={t("Open post")}><ExternalLink size={12} /></a>}
                      </span>
                    ))}
                  </div>
                  {p.targets.filter((x) => x.error).map((x) => (
                    <p key={x.account.id} className="mt-1 text-xs text-red-700"><b>{x.account.name}:</b> {x.error}</p>
                  ))}
                  {p.targets.filter((x) => x.options.note).map((x) => (
                    <p key={x.account.id} className="mt-1 text-xs text-slate-500"><b>{x.account.name}:</b> {x.options.note}</p>
                  ))}
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  {busy === p.id ? <LoaderCircle className="m-2 animate-spin text-slate-400" size={16} /> : (
                    <>
                      {editable && <button type="button" className="btn-ghost px-2" title={t("Edit")} onClick={() => onEdit(p)}><Pencil size={16} /></button>}
                      {retryable && can("publish_posts") && (
                        <button type="button" className="btn-ghost px-2" title={t("Retry failed platforms")} onClick={() => act(p.id, () => Api.retryPost(p.id))}><RotateCcw size={16} /></button>
                      )}
                      {p.status !== "publishing" && (
                        <button type="button" className="btn-ghost px-2 text-red-600" title={t("Delete from OmniInbox")}
                          onClick={() => { if (window.confirm(t("Delete this post from OmniInbox? Already-published posts stay on the platforms."))) act(p.id, () => Api.deletePost(p.id)); }}>
                          <Trash2 size={16} />
                        </button>
                      )}
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
