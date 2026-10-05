"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { CalendarClock, Check, CircleAlert, Film, ImagePlus, LoaderCircle, Send, Sparkles, Trash, TriangleAlert, X } from "lucide-react";
import { Api } from "@/lib/api";
import type { MediaAsset, PublishConfig, PublishPlatform, SocialAccount, SocialPost, TikTokCreator } from "@/lib/types";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { useMe } from "@/components/AppShell";
import { useT } from "@/lib/i18n";
import PlatformCard from "./PlatformCard";
import PublishResults from "./PublishResults";
import { blockers, defaultOpts, fmtDuration, hints, loadRemembered, remember, shape, type TargetState } from "./platform";

type Creator = TikTokCreator | "loading" | { error: string };

function toLocalInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function Preview({ platform, account, caption, media, title, tags }: {
  platform: PublishPlatform; account: SocialAccount; caption: string; media: MediaAsset | null; title: string; tags: string[];
}) {
  const t = useT();
  const vertical = platform === "tiktok" || (platform === "instagram" && media?.kind === "video") || (platform === "youtube" && shape(media) === "vertical");
  const mediaEl = media ? (
    media.kind === "image"
      // eslint-disable-next-line @next/next/no-img-element
      ? <img src={media.preview_url} alt="" className="h-full w-full object-cover" />
      : <video src={media.preview_url} className="h-full w-full object-cover" muted playsInline controls />
  ) : null;
  return (
    <div className={clsx("overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm", vertical ? "mx-auto max-w-[260px]" : "")}>
      <div className="flex items-center gap-2 px-3 py-2">
        <ProviderIcon provider={platform} size="sm" />
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold">{account.name}</p>
          <p className="text-[10px] text-slate-500">{t("{name} preview", { name: providerUI(platform).label })}</p>
        </div>
      </div>
      {mediaEl && <div className={clsx("bg-slate-900", vertical ? "aspect-[9/16]" : platform === "youtube" ? "aspect-video" : "aspect-square")}>{mediaEl}</div>}
      {platform === "youtube" && <p className="px-3 pt-2 text-sm font-semibold">{title || t("Video title")}</p>}
      <p className="line-clamp-[12] whitespace-pre-wrap break-words px-3 py-2 text-xs text-slate-700">{caption || <span className="text-slate-400">{t("Your caption…")}</span>}</p>
      {platform === "youtube" && tags.length > 0 && <p className="px-3 pb-2 text-[10px] text-slate-400">{tags.map((x) => `#${x.replace(/\s+/g, "")}`).join(" ")}</p>}
    </div>
  );
}

export default function Composer({ accounts, cfg, editing, onDone, onFresh }: {
  accounts: SocialAccount[]; cfg: PublishConfig; editing: SocialPost | null; onDone: (msg: string) => void; onFresh?: () => void;
}) {
  const t = useT();
  const { can, hasFeature } = useMe();
  const [selected, setSelected] = useState<string[]>(() => editing?.targets.map((x) => x.account.id) ?? []);
  const [caption, setCaption] = useState(editing?.caption ?? "");
  const [media, setMedia] = useState<MediaAsset | null>(editing?.media ?? null);
  const [targets, setTargets] = useState<Record<string, TargetState>>(() => Object.fromEntries((editing?.targets ?? []).map((x) => [
    x.account.id, { caption: x.caption, custom: !!x.caption, opts: { ...defaultOpts(x.account.platform), ...x.options } },
  ])));
  const [open, setOpen] = useState<string | null>(null);
  const [creators, setCreators] = useState<Record<string, Creator>>({});
  const [ai, setAi] = useState({ brief: "", language: "english", busy: false, summary: "", checks: [] as string[] });
  const [showWhen, setShowWhen] = useState(false);
  const [schedule, setSchedule] = useState(editing?.scheduled_at && editing.status === "scheduled" ? toLocalInput(new Date(editing.scheduled_at)) : "");
  const [uploading, setUploading] = useState<number | null>(null);
  const [busy, setBusy] = useState<"" | "draft" | "publish" | "schedule">("");
  const [error, setError] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const chosen = accounts.filter((a) => selected.includes(a.id));
  const target = (a: SocialAccount): TargetState => targets[a.id] ?? { caption: "", custom: false, opts: { ...defaultOpts(a.platform), ...loadRemembered(a.id) } };
  const patchTarget = (a: SocialAccount, patch: Partial<TargetState>) => setTargets((all) => ({ ...all, [a.id]: { ...(all[a.id] ?? target(a)), ...patch } }));
  const textFor = (a: SocialAccount) => (target(a).custom ? target(a).caption : caption);
  const creatorOf = (a: SocialAccount) => {
    const c = creators[a.id];
    return c && c !== "loading" && !("error" in c) ? c : null;
  };
  const problems = useMemo(() => Object.fromEntries(chosen.map((a) => [a.id, blockers(a.platform, cfg, textFor(a), media, target(a), t, creatorOf(a))])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [chosen, cfg, caption, media, targets, creators, t]);
  const blocked = Object.values(problems).some((v) => v.length > 0);
  const preview = chosen.find((a) => a.id === previewId) ?? chosen[0];

  function toggleAccount(a: SocialAccount) {
    if (selected.includes(a.id)) { setSelected(selected.filter((x) => x !== a.id)); return; }
    setSelected([...selected, a.id]);
    setTargets((all) => (all[a.id] ? all : { ...all, [a.id]: { caption: "", custom: false, opts: { ...defaultOpts(a.platform), ...loadRemembered(a.id) } } }));
    if (a.platform === "tiktok" && !creators[a.id]) {
      setCreators((c) => ({ ...c, [a.id]: "loading" }));
      Api.tiktokCreator(a.id)
        .then((info) => setCreators((c) => ({ ...c, [a.id]: info })))
        .catch((e) => setCreators((c) => ({ ...c, [a.id]: { error: e instanceof Error ? e.message : t("Couldn't reach TikTok") } })));
    }
  }

  useEffect(() => {
    if (previewId && !selected.includes(previewId)) setPreviewId(null);
  }, [selected, previewId]);

  async function fillWithAI() {
    setError("");
    setAi((s) => ({ ...s, busy: true }));
    try {
      const platforms = Array.from(new Set(chosen.map((a) => a.platform)));
      const res = await Api.aiPublishFill({ media_id: media?.id ?? null, brief: ai.brief, platforms, language: ai.language });
      // The main text: Facebook's caption if there is one, else the first platform's
      const main = res.facebook?.caption || res.instagram?.caption || res.tiktok?.caption || res.youtube?.description || caption;
      setCaption(main);
      setTargets((all) => {
        const next = { ...all };
        for (const a of chosen) {
          const cur = next[a.id] ?? target(a);
          let own = "";
          let opts = cur.opts;
          if (a.platform === "youtube" && res.youtube) {
            own = res.youtube.description;
            opts = { ...opts, title: res.youtube.title || opts.title, tags: res.youtube.tags.length ? res.youtube.tags : opts.tags, category_id: res.youtube.category_id || opts.category_id };
          } else if (a.platform === "instagram") own = res.instagram?.caption ?? "";
          else if (a.platform === "tiktok") own = res.tiktok?.caption ?? "";
          else if (a.platform === "facebook") {
            own = res.facebook?.caption ?? "";
            if (res.facebook?.title) opts = { ...opts, title: res.facebook.title };
          }
          next[a.id] = { ...cur, opts, custom: !!own && own !== main, caption: own && own !== main ? own : cur.caption };
        }
        return next;
      });
      setAi((s) => ({ ...s, busy: false, summary: res.summary, checks: res.checks }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("AI couldn't write the post"));
      setAi((s) => ({ ...s, busy: false }));
    }
  }

  async function upload(file: File) {
    setError("");
    setUploading(0);
    try {
      setMedia(await Api.uploadMedia(file, setUploading));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Upload failed"));
    } finally {
      setUploading(null);
    }
  }

  async function submit(action: "draft" | "publish" | "schedule") {
    setError("");
    if (action !== "draft" && blocked) {
      const first = chosen.find((a) => problems[a.id]?.length);
      if (first) setOpen(first.id);
      setError(t("Fix what's marked on each platform first."));
      return;
    }
    if (action === "schedule" && !schedule) {
      setError(t("Pick a date and time to schedule."));
      return;
    }
    setBusy(action);
    try {
      const saved = await Api.savePost(editing?.id ?? null, {
        caption, media_id: media?.id ?? null, action,
        scheduled_at: action === "schedule" ? new Date(schedule).toISOString() : null,
        targets: chosen.map((a) => {
          const ts = target(a);
          return { account_id: a.id, caption: ts.custom ? ts.caption : "", options: ts.opts };
        }),
      });
      if (action !== "draft") chosen.forEach((a) => remember(a.id, target(a).opts));
      if (action === "publish") setResultId(saved.id);
      else onDone(action === "schedule" ? t("Scheduled for {when}.", { when: new Date(schedule).toLocaleString() }) : t("Draft saved."));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Couldn't save the post"));
    } finally {
      setBusy("");
    }
  }

  if (accounts.length === 0) {
    return <p className="card p-6 text-sm text-slate-600">{t("Connect a Facebook Page, Instagram, YouTube or TikTok account in the Accounts tab to start posting.")}</p>;
  }
  if (resultId) {
    return <PublishResults postId={resultId} onNew={() => (onFresh ? onFresh() : onDone(""))} onPosts={() => onDone("")} />;
  }

  const facts = media ? [
    media.kind === "video" && media.duration ? fmtDuration(media.duration) : "",
    media.width && media.height ? `${media.width}×${media.height}` : "",
    { vertical: t("Vertical"), horizontal: t("Horizontal"), square: t("Square"), "": "" }[shape(media)],
    `${(media.size / 1048576).toFixed(1)} MB`,
  ].filter(Boolean).join(" · ") : "";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-4">
        {/* 1. media */}
        <div className="card p-4">
          <p className="text-sm font-semibold">{t("1. Video or photo")}</p>
          <div className="mt-3">
            {media ? (
              <div className="flex items-center gap-3 rounded-lg border border-slate-200 p-2">
                <div className="h-16 w-16 shrink-0 overflow-hidden rounded-md bg-slate-900">
                  {media.kind === "image"
                    // eslint-disable-next-line @next/next/no-img-element
                    ? <img src={media.preview_url} alt="" className="h-full w-full object-cover" />
                    : <video src={media.preview_url} className="h-full w-full object-cover" muted />}
                </div>
                <div className="min-w-0 flex-1 text-sm">
                  <p className="truncate font-medium">{media.name || t(media.kind === "image" ? "Image file" : "Video file")}</p>
                  <p className="flex items-center gap-1 text-xs text-slate-500">{media.kind === "video" && <Film size={12} />} {facts}</p>
                </div>
                <button type="button" className="btn-ghost px-2" onClick={() => setMedia(null)} aria-label={t("Remove media")}><Trash size={16} /></button>
              </div>
            ) : (
              <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading !== null}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) upload(f); }}
                className="flex w-full flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-slate-300 py-7 text-sm text-slate-500 hover:border-brand-500 hover:text-brand-700">
                {uploading !== null ? (
                  <>
                    <LoaderCircle className="animate-spin" size={20} /> {t("Uploading… {pct}%", { pct: uploading })}
                    <span className="mt-1 h-1.5 w-40 overflow-hidden rounded-full bg-slate-200"><span className="block h-full bg-brand-600" style={{ width: `${uploading}%` }} /></span>
                  </>
                ) : (
                  <>
                    <ImagePlus size={22} /> {t("Upload once, post everywhere")}
                    <span className="text-xs text-slate-400">{t("MP4/MOV up to 500 MB · JPEG/PNG up to 8 MB")}</span>
                  </>
                )}
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,video/mp4,video/quicktime" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
          </div>
        </div>

        {/* 2. accounts */}
        <div className="card p-4">
          <p className="text-sm font-semibold">{t("2. Post to")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {accounts.map((a) => {
              const on = selected.includes(a.id);
              return (
                <button key={a.id} type="button" onClick={() => toggleAccount(a)}
                  className={clsx("flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-sm transition",
                    on ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600 hover:border-slate-300",
                    a.status === "error" && "opacity-60")}
                  title={a.status === "error" ? a.last_error : ""}>
                  <ProviderIcon provider={a.platform} size="sm" className="rounded-full" />
                  <span className="max-w-[160px] truncate">{a.name}</span>
                  {on && <Check size={14} />}
                </button>
              );
            })}
          </div>
        </div>

        {/* 3. text (+ AI) */}
        <div className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="text-sm font-semibold" htmlFor="caption">{t("3. Text")}</label>
            {chosen.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {chosen.map((a) => {
                  const lim = cfg.limits[a.platform].caption, len = textFor(a).length;
                  return (
                    <span key={a.id} className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]", len > lim ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-600")}>
                      <ProviderIcon provider={a.platform} size="xs" /> {len}/{lim.toLocaleString()}
                    </span>
                  );
                })}
              </div>
            )}
          </div>

          {hasFeature("ai_assist") && (
            <div className="mt-3 rounded-xl border border-brand-100 bg-gradient-to-br from-brand-50 to-white p-3">
              <div className="flex flex-col gap-2 sm:flex-row">
                <input className="input flex-1 bg-white" maxLength={2000} value={ai.brief} onChange={(e) => setAi({ ...ai, brief: e.target.value })}
                  placeholder={media?.kind === "video" ? t("Optional: anything to mention? e.g. 20% off until Friday") : t("What's the post about? e.g. Dashain sale: 20% off kurtas")} />
                <select className="input py-2 sm:w-auto" value={ai.language} onChange={(e) => setAi({ ...ai, language: e.target.value })} aria-label={t("Language")}>
                  <option value="english">English</option><option value="nepali">नेपाली</option>
                  <option value="romanized">{t("Romanized Nepali")}</option><option value="mixed">{t("English + Nepali mix")}</option>
                </select>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button type="button" className="btn-primary" disabled={ai.busy || chosen.length === 0 || (!media && ai.brief.trim().length < 5)} onClick={fillWithAI}>
                  {ai.busy ? <LoaderCircle className="animate-spin" size={16} /> : <Sparkles size={16} />}
                  {ai.busy ? (media?.kind === "video" ? t("Watching your video…") : t("Writing…")) : t("Fill everything with AI")}
                </button>
                <span className="text-xs text-slate-500">
                  {chosen.length === 0 ? t("Pick where to post first.")
                    : media?.kind === "video" ? t("Watches and listens to the video, then writes titles, tags and captions for each platform. 2 credits.")
                    : t("Writes the text for each platform. 1 credit.")}
                </span>
              </div>
              {ai.summary && <p className="mt-2 text-xs text-slate-600"><b>{t("AI saw:")}</b> {ai.summary}</p>}
              {ai.checks.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {ai.checks.map((c) => <li key={c} className="flex items-start gap-1.5 text-xs text-amber-800"><TriangleAlert size={13} className="mt-0.5 shrink-0" /> {c}</li>)}
                </ul>
              )}
            </div>
          )}

          <textarea id="caption" className="input mt-3 min-h-[130px]" value={caption} maxLength={5000}
            placeholder={t("Write your post once… #hashtags and @mentions work as usual")} onChange={(e) => setCaption(e.target.value)} />
        </div>

        {/* 4. per platform */}
        {chosen.length > 0 && (
          <div className="space-y-2">
            <p className="px-1 text-sm font-semibold">{t("4. Check each platform")}</p>
            {chosen.map((a) => (
              <PlatformCard key={a.id} account={a} cfg={cfg} ts={target(a)} caption={caption} media={media}
                problems={problems[a.id] ?? []} tips={hints(a.platform, media, t)} creator={creators[a.id]}
                open={open === a.id} onToggleOpen={() => { setOpen(open === a.id ? null : a.id); setPreviewId(a.id); }}
                onChange={(patch) => patchTarget(a, patch)} />
            ))}
          </div>
        )}

        {error && <p className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"><CircleAlert size={16} className="mt-0.5 shrink-0" /> {error}</p>}

        {/* publish bar: compact so it doesn't cover the form on phones */}
        <div className="card sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-10 space-y-2 p-2.5 sm:p-3 md:bottom-2">
          {(showWhen || schedule) && (
            <div className="flex items-center gap-1">
              <input id="when" type="datetime-local" className="input min-w-0" value={schedule} min={toLocalInput(new Date())}
                aria-label={t("Schedule for")} onChange={(e) => setSchedule(e.target.value)} />
              <button type="button" className="btn-ghost px-2" onClick={() => { setSchedule(""); setShowWhen(false); }} aria-label={t("Don't schedule")}><X size={16} /></button>
            </div>
          )}
          <div className="flex items-center gap-2">
            <button type="button" className={clsx("btn-secondary px-2.5", (showWhen || schedule) && "border-brand-500 text-brand-700")}
              disabled={!cfg.features.schedule} onClick={() => setShowWhen(!showWhen)}
              title={cfg.features.schedule ? t("Schedule for later") : t("Scheduling is on Pro and higher.")} aria-label={t("Schedule for later")}>
              <CalendarClock size={18} />
            </button>
            {editing && <button type="button" className="btn-ghost px-2 text-slate-500 lg:hidden" onClick={() => onDone("")}>{t("Cancel")}</button>}
            <span className="flex-1" />
            <button type="button" className="btn-secondary" disabled={!!busy || chosen.length === 0} onClick={() => submit("draft")}>
              {busy === "draft" && <LoaderCircle className="animate-spin" size={16} />} {t("Draft")}
            </button>
            {can("publish_posts") ? (
              schedule ? (
                <button type="button" className="btn-primary" disabled={!!busy || chosen.length === 0} onClick={() => submit("schedule")}>
                  {busy === "schedule" ? <LoaderCircle className="animate-spin" size={16} /> : <CalendarClock size={16} />} {t("Schedule")}
                </button>
              ) : (
                <button type="button" className="btn-primary" disabled={!!busy || chosen.length === 0} onClick={() => submit("publish")}>
                  {busy === "publish" ? <LoaderCircle className="animate-spin" size={16} /> : <Send size={16} />}
                  {chosen.length > 1 ? t("Publish to all {n}", { n: chosen.length }) : t("Publish now")}
                </button>
              )
            ) : <span className="text-xs text-slate-500">{t("A supervisor or admin publishes.")}</span>}
          </div>
        </div>
      </div>

      <div className="hidden space-y-3 lg:sticky lg:top-4 lg:block lg:self-start">
        <p className="text-sm font-semibold">{t("Preview")}</p>
        {chosen.length > 1 && (
          <div className="flex flex-wrap gap-1">
            {chosen.map((a) => (
              <button key={a.id} type="button" onClick={() => setPreviewId(a.id)}
                className={clsx("rounded-full p-0.5", (preview?.id === a.id) ? "ring-2 ring-brand-500" : "opacity-60 hover:opacity-100")}>
                <ProviderIcon provider={a.platform} size="sm" className="rounded-full" />
              </button>
            ))}
          </div>
        )}
        {preview ? (
          <Preview platform={preview.platform} account={preview} caption={textFor(preview)} media={media}
            title={target(preview).opts.title ?? ""} tags={target(preview).opts.tags ?? []} />
        ) : <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">{t("Pick an account to see a preview")}</p>}
        {editing && <button type="button" className="btn-ghost w-full text-slate-500" onClick={() => onDone("")}><X size={16} /> {t("Cancel editing")}</button>}
      </div>
    </div>
  );
}
