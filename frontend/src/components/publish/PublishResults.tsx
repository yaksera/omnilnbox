"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { CircleCheck, CircleX, ExternalLink, LoaderCircle, PartyPopper, RotateCcw } from "lucide-react";
import { Api } from "@/lib/api";
import type { SocialPost } from "@/lib/types";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { useT } from "@/lib/i18n";

/** Live progress after "Publish all": one line per platform, with a link to the live post when it's done. */
export default function PublishResults({ postId, onNew, onPosts }: { postId: string; onNew: () => void; onPosts: () => void }) {
  const t = useT();
  const [post, setPost] = useState<SocialPost | null>(null);
  const [retrying, setRetrying] = useState(false);
  const done = post && !["scheduled", "publishing"].includes(post.status);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const p = await Api.post(postId);
        if (stop) return;
        setPost(p);
        if (["scheduled", "publishing"].includes(p.status)) timer = setTimeout(tick, 2500);
      } catch {
        if (!stop) timer = setTimeout(tick, 5000);
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [postId, retrying]);

  const ok = post?.targets.filter((x) => x.status === "published").length ?? 0;
  const total = post?.targets.length ?? 0;

  return (
    <div className="card mx-auto max-w-xl p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <span className={clsx("flex h-11 w-11 items-center justify-center rounded-full",
          !done ? "bg-brand-50 text-brand-600" : ok === total ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-600")}>
          {!done ? <LoaderCircle className="animate-spin" size={22} /> : ok === total ? <PartyPopper size={22} /> : <CircleX size={22} />}
        </span>
        <div>
          <p className="text-lg font-semibold">
            {!done ? t("Publishing to {n} places…", { n: total || "…" }) : ok === total ? t("Published everywhere!") : t("Published to {ok} of {total}", { ok, total })}
          </p>
          <p className="text-sm text-slate-500">{!done ? t("You can leave this page. Videos keep uploading in the background.")
            : ok === total ? t("Here's where your post is live.") : ok === 0 ? t("Nothing was published. The reasons are below.") : t("Check the ones that failed below.")}</p>
        </div>
      </div>

      <ul className="mt-5 divide-y divide-slate-100 rounded-xl border border-slate-200">
        {(post?.targets ?? []).map((x) => (
          <li key={x.account.id} className="flex items-center gap-3 px-3 py-2.5">
            <ProviderIcon provider={x.account.platform} size="sm" className="rounded-full" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{x.account.name}</span>
              <span className={clsx("block text-xs", x.status === "failed" ? "text-red-700" : "text-slate-500")}>
                {x.status === "published" ? (x.options.note || t("Live on {platform}", { platform: providerUI(x.account.platform).label }))
                  : x.status === "failed" ? x.error.slice(0, 200)
                  : x.status === "publishing" ? t("Uploading…") : t("Waiting…")}
              </span>
            </span>
            {x.status === "published" && x.url && (
              <a href={x.url} target="_blank" rel="noopener noreferrer" className="btn-secondary px-2.5 py-1 text-xs"><ExternalLink size={13} /> {t("Open")}</a>
            )}
            {x.status === "published" && !x.url && <CircleCheck size={18} className="text-emerald-600" />}
            {(x.status === "publishing" || x.status === "pending") && <LoaderCircle size={18} className="animate-spin text-slate-400" />}
            {x.status === "failed" && <CircleX size={18} className="text-red-600" />}
          </li>
        ))}
        {!post && <li className="flex justify-center p-4 text-slate-400"><LoaderCircle className="animate-spin" /></li>}
      </ul>

      <div className="mt-5 flex flex-wrap gap-2">
        {done && ok < total && (
          <button type="button" className="btn-secondary" disabled={retrying}
            onClick={async () => { setRetrying(true); try { await Api.retryPost(postId); } finally { setRetrying(false); } }}>
            <RotateCcw size={16} /> {t("Retry failed")}
          </button>
        )}
        <button type="button" className="btn-primary" onClick={onNew}>{t("Create another post")}</button>
        <button type="button" className="btn-ghost" onClick={onPosts}>{t("See all posts")}</button>
      </div>
    </div>
  );
}
