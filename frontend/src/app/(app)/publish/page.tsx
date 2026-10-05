"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { CalendarDays, CheckCircle2, List, LoaderCircle, PenSquare, Settings2 } from "lucide-react";
import { Api } from "@/lib/api";
import type { PublishConfig, SocialAccount, SocialPost } from "@/lib/types";
import { ProviderIcon } from "@/lib/providers";
import { UpgradeHint } from "@/components/AppShell";
import { useT } from "@/lib/i18n";
import Composer from "@/components/publish/Composer";
import PostsList from "@/components/publish/PostsList";
import Calendar from "@/components/publish/Calendar";

type Tab = "compose" | "posts" | "calendar";

export default function PublishPage() {
  const t = useT();
  const [tab, setTab] = useState<Tab>("compose");
  const [cfg, setCfg] = useState<PublishConfig | null>(null);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [editing, setEditing] = useState<SocialPost | null>(null);
  const [composerKey, setComposerKey] = useState(0);
  const [flash, setFlash] = useState("");
  const [error, setError] = useState("");

  const loadPosts = useCallback(() => Api.posts().then(setPosts).catch(() => {}), []);

  useEffect(() => {
    Promise.all([Api.publishConfig(), Api.socialAccounts()])
      .then(([c, a]) => { setCfg(c); setAccounts(a); })
      .catch((e) => setError(e instanceof Error ? e.message : t("Couldn't load publishing")));
    loadPosts();
  }, [loadPosts, t]);

  // Keep statuses fresh while something is publishing.
  useEffect(() => {
    if (!posts.some((p) => p.status === "publishing")) return;
    const timer = setInterval(loadPosts, 4000);
    return () => clearInterval(timer);
  }, [posts, loadPosts]);

  function edit(p: SocialPost) {
    setEditing(p);
    setComposerKey((k) => k + 1);
    setTab("compose");
  }

  function done(msg: string) {
    setEditing(null);
    setComposerKey((k) => k + 1);
    loadPosts();
    if (msg) { setFlash(msg); setTab("posts"); setTimeout(() => setFlash(""), 5000); } else setTab("posts");
  }

  if (error) return <div className="p-6"><p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p></div>;
  if (!cfg) return <div className="flex h-full items-center justify-center"><LoaderCircle className="animate-spin text-slate-400" /></div>;

  const TABS: Array<[Tab, string, typeof List]> = [["compose", editing ? "Edit post" : "Create post", PenSquare], ["posts", "Posts", List], ["calendar", "Calendar", CalendarDays]];
  const scheduled = posts.filter((p) => p.status === "scheduled").length;

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">{t("Publish")}</h1>
          <p className="text-sm text-slate-500">{t("Upload once, let AI write for each platform, and publish to Facebook, Instagram, YouTube and TikTok in one click.")}</p>
        </div>
        <Link href="/publish/accounts" className="btn-secondary">
          <span className="flex -space-x-1">
            {accounts.slice(0, 4).map((a) => <ProviderIcon key={a.id} provider={a.platform} size="xs" className="rounded-full ring-2 ring-white" />)}
          </span>
          <Settings2 size={16} /> {t("Accounts ({n})", { n: accounts.length })}
        </Link>
      </div>

      {!cfg.features.publish && (
        <div className="mt-4">
          <UpgradeHint feature={t("Social publishing")}>{t("Post to your pages and channels from OmniInbox on the Starter plan and above. Scheduling is on Pro and above.")}</UpgradeHint>
        </div>
      )}

      <div className="mt-5 flex gap-1 border-b border-slate-200">
        {TABS.map(([key, label, Icon]) => (
          <button key={key} type="button" onClick={() => setTab(key)}
            className={clsx("-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
              tab === key ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800")}>
            <Icon size={16} /> {t(label)}
            {key === "posts" && scheduled > 0 && <span className="rounded-full bg-sky-100 px-1.5 text-[10px] text-sky-700">{t("{n} scheduled", { n: scheduled })}</span>}
          </button>
        ))}
      </div>

      {flash && <p className="mt-4 flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800"><CheckCircle2 size={16} /> {flash}</p>}

      <div className="mt-5">
        {tab === "compose" && (cfg.features.publish
          ? <Composer key={composerKey} accounts={accounts} cfg={cfg} editing={editing} onDone={done}
              onFresh={() => { setEditing(null); setComposerKey((k) => k + 1); loadPosts(); }} />
          : <p className="text-sm text-slate-500">{t("Upgrade to start publishing.")}</p>)}
        {tab === "posts" && <PostsList posts={posts} onEdit={edit} onChanged={loadPosts} />}
        {tab === "calendar" && <Calendar refreshKey={posts.length} onOpen={(p) => (p.status === "draft" || p.status === "scheduled" ? edit(p) : setTab("posts"))} />}
      </div>
    </div>
  );
}
