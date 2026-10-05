"use client";

import { useState } from "react";
import clsx from "clsx";
import { Check, ChevronDown, CircleAlert, Info, LoaderCircle, X } from "lucide-react";
import type { MediaAsset, PublishConfig, PublishOptions, SocialAccount, TikTokCreator } from "@/lib/types";
import { ProviderIcon, providerUI } from "@/lib/providers";
import { useT } from "@/lib/i18n";
import { TIKTOK_PRIVACY, type TargetState } from "./platform";

function Toggle({ label, checked, onChange, disabled, help }: { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; help?: string }) {
  return (
    <label className={clsx("flex items-start gap-2 text-sm", disabled && "opacity-50")}>
      <input type="checkbox" className="mt-0.5 accent-brand-600" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}{help && <span className="block text-xs text-slate-500">{help}</span>}</span>
    </label>
  );
}

function Segmented({ value, options, onChange }: { value: string; options: Array<[string, string]>; onChange: (v: string) => void }) {
  return (
    <div className="flex rounded-lg bg-slate-100 p-0.5 text-sm">
      {options.map(([v, l]) => (
        <button key={v} type="button" onClick={() => onChange(v)}
          className={clsx("flex-1 rounded-md px-2.5 py-1.5 font-medium transition", value === v ? "bg-white text-slate-900 shadow-sm" : "text-slate-500")}>{l}</button>
      ))}
    </div>
  );
}

/** Tags typed as "kurta, dashain" or Enter; shown as chips. */
function TagInput({ tags, onChange, placeholder }: { tags: string[]; onChange: (t: string[]) => void; placeholder: string }) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const next = [...tags];
    for (const p of raw.split(",")) {
      const v = p.replace(/#/g, "").trim();
      if (v && !next.some((x) => x.toLowerCase() === v.toLowerCase())) next.push(v.slice(0, 60));
    }
    onChange(next.slice(0, 40));
    setDraft("");
  };
  return (
    <div className="flex min-h-[42px] flex-wrap items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2 py-1.5 focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-500">
      {tags.map((tg) => (
        <span key={tg} className="inline-flex items-center gap-1 rounded-full bg-slate-100 py-0.5 pl-2 pr-1 text-xs">
          {tg}<button type="button" onClick={() => onChange(tags.filter((x) => x !== tg))} className="rounded-full p-0.5 hover:bg-slate-200" aria-label={`× ${tg}`}><X size={11} /></button>
        </span>
      ))}
      <input className="min-w-[120px] flex-1 border-0 bg-transparent p-0.5 text-sm outline-none" value={draft} placeholder={tags.length ? "" : placeholder}
        onChange={(e) => (e.target.value.includes(",") ? add(e.target.value) : setDraft(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); add(draft); }
          if (e.key === "Backspace" && !draft && tags.length) onChange(tags.slice(0, -1));
        }}
        onBlur={() => draft && add(draft)} />
    </div>
  );
}

export default function PlatformCard({ account, cfg, ts, caption, media, problems, tips, creator, onChange, open, onToggleOpen }: {
  account: SocialAccount; cfg: PublishConfig; ts: TargetState; caption: string; media: MediaAsset | null; problems: string[]; tips: string[];
  creator?: TikTokCreator | null | "loading" | { error: string };
  onChange: (patch: Partial<TargetState>) => void; open: boolean; onToggleOpen: () => void;
}) {
  const t = useT();
  const [more, setMore] = useState(false);
  const o = ts.opts;
  const set = (patch: PublishOptions) => onChange({ opts: { ...o, ...patch } });
  const p = account.platform;
  const label = providerUI(p).label;
  const isVideo = media?.kind === "video";
  const info = creator && creator !== "loading" && !("error" in creator) ? creator : null;
  const textLimit = cfg.limits[p].caption;
  const textLen = (ts.custom ? ts.caption : caption).length;

  return (
    <div className={clsx("card overflow-hidden", problems.length > 0 && "ring-1 ring-amber-300")}>
      <button type="button" onClick={onToggleOpen} className="flex w-full items-center gap-2.5 px-4 py-3 text-left">
        <ProviderIcon provider={p} size="sm" className="rounded-full" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold">{account.name}</span>
          <span className="block truncate text-xs text-slate-500">
            {p === "youtube" ? (o.title || t("Add a title")) : (ts.custom ? t("Own text") : t("Main text"))} · {textLen}/{textLimit.toLocaleString()}
          </span>
        </span>
        {problems.length === 0
          ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700"><Check size={13} /> {t("Ready")}</span>
          : <span className="inline-flex max-w-[45%] items-center gap-1 truncate rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800"><CircleAlert size={13} className="shrink-0" /> <span className="truncate">{problems[0]}</span></span>}
        <ChevronDown size={16} className={clsx("shrink-0 text-slate-400 transition", open && "rotate-180")} />
      </button>

      {open && (
        <div className="space-y-3 border-t border-slate-100 px-4 py-3">
          {problems.length > 1 && <ul className="space-y-0.5 text-xs text-amber-800">{problems.slice(1).map((x) => <li key={x}>• {x}</li>)}</ul>}
          {tips.map((x) => <p key={x} className="flex items-start gap-1.5 rounded-lg bg-sky-50 px-2.5 py-1.5 text-xs text-sky-800"><Info size={13} className="mt-0.5 shrink-0" /> {x}</p>)}

          {/* ---------------- essentials ---------------- */}
          {p === "youtube" && (
            <>
              <label className="block text-sm">{t("Title")} <span className="text-xs text-slate-400">{(o.title ?? "").length}/100</span>
                <input className="input mt-1" maxLength={100} value={o.title ?? ""} placeholder={t("What viewers will search for")} onChange={(e) => set({ title: e.target.value })} />
              </label>
              <Segmented value={o.privacy ?? "public"} onChange={(v) => set({ privacy: v })}
                options={[["public", t("Public")], ["unlisted", t("Unlisted")], ["private", t("Private")]]} />
              <div className="text-sm">{t("Tags")}
                <div className="mt-1"><TagInput tags={o.tags ?? []} onChange={(tags) => set({ tags })} placeholder={t("kurta, dashain sale… (Enter to add)")} /></div>
              </div>
            </>
          )}
          {p === "tiktok" && (
            <>
              {creator === "loading" && <p className="flex items-center gap-1.5 text-xs text-slate-500"><LoaderCircle size={13} className="animate-spin" /> {t("Checking your TikTok account…")}</p>}
              {creator && creator !== "loading" && "error" in creator && <p className="text-xs text-red-700">{creator.error}</p>}
              {info && <p className="text-xs text-slate-500">{t("Posting to {name} on TikTok", { name: info.nickname })}</p>}
              <label className="block text-sm">{t("Who can see this video")}
                <select className="input mt-1" value={o.privacy ?? ""} onChange={(e) => set({ privacy: e.target.value })}>
                  <option value="" disabled>{t("Choose…")}</option>
                  {(info?.privacy_options ?? Object.keys(TIKTOK_PRIVACY)).map((v) => <option key={v} value={v}>{t(TIKTOK_PRIVACY[v] ?? v)}</option>)}
                </select>
              </label>
            </>
          )}

          <Toggle label={t("Write different text for {platform}", { platform: label })} checked={ts.custom}
            onChange={(v) => onChange({ custom: v, caption: ts.caption || caption })} />
          {ts.custom && (
            <textarea className="input min-h-[90px]" maxLength={textLimit} value={ts.caption} onChange={(e) => onChange({ caption: e.target.value })}
              placeholder={p === "youtube" ? t("Video description") : t("Text for {platform}", { platform: label })} />
          )}
          {p === "youtube" && !ts.custom && <p className="text-xs text-slate-500">{t("The main text is used as the video description.")}</p>}

          {/* ---------------- more options ---------------- */}
          <button type="button" onClick={() => setMore(!more)} className="inline-flex items-center gap-1 text-xs font-medium text-brand-700">
            <ChevronDown size={14} className={clsx("transition", more && "rotate-180")} /> {more ? t("Fewer options") : t("More options")}
          </button>
          {more && (
            <div className="space-y-3 rounded-xl bg-slate-50 p-3">
              {p === "youtube" && (
                <>
                  <label className="block text-sm">{t("Category")}
                    <select className="input mt-1" value={o.category_id ?? "22"} onChange={(e) => set({ category_id: e.target.value })}>
                      {Object.entries(cfg.youtube_categories ?? { 22: "People & Blogs" }).map(([id, name]) => <option key={id} value={id}>{t(name)}</option>)}
                    </select>
                  </label>
                  <div className="text-sm">{t("Is this video made for kids?")}
                    <div className="mt-1"><Segmented value={o.made_for_kids ? "yes" : "no"} onChange={(v) => set({ made_for_kids: v === "yes" })}
                      options={[["no", t("No, it's not made for kids")], ["yes", t("Yes")]]} /></div>
                    <span className="mt-1 block text-xs text-slate-500">{t("Required by YouTube (COPPA). Videos for kids lose comments and some features.")}</span>
                  </div>
                  <Toggle label={t("Notify subscribers")} checked={o.notify_subscribers ?? true} onChange={(v) => set({ notify_subscribers: v })} />
                </>
              )}
              {p === "tiktok" && (
                <>
                  <p className="text-xs font-medium text-slate-600">{t("Allow viewers to")}</p>
                  <div className="flex flex-wrap gap-4">
                    <Toggle label={t("Comment")} checked={!o.disable_comment && !info?.comment_disabled} disabled={info?.comment_disabled} onChange={(v) => set({ disable_comment: !v })} />
                    <Toggle label={t("Duet")} checked={!o.disable_duet && !info?.duet_disabled} disabled={info?.duet_disabled} onChange={(v) => set({ disable_duet: !v })} />
                    <Toggle label={t("Stitch")} checked={!o.disable_stitch && !info?.stitch_disabled} disabled={info?.stitch_disabled} onChange={(v) => set({ disable_stitch: !v })} />
                  </div>
                  <Toggle label={t("This video promotes a brand, product or service")} checked={!!(o.brand_organic || o.brand_content)}
                    onChange={(v) => set(v ? { brand_organic: true } : { brand_organic: false, brand_content: false })} />
                  {(o.brand_organic || o.brand_content) && (
                    <div className="ml-6 space-y-2">
                      <Toggle label={t("Your brand")} help={t("You're promoting yourself or your own business. Labelled “Promotional content”.")}
                        checked={!!o.brand_organic} onChange={(v) => set({ brand_organic: v })} />
                      <Toggle label={t("Branded content")} help={t("You're promoting another brand (paid partnership). Labelled “Paid partnership”; can't be private.")}
                        checked={!!o.brand_content} onChange={(v) => set({ brand_content: v })} />
                    </div>
                  )}
                </>
              )}
              {p === "instagram" && (
                <>
                  {isVideo && <Toggle label={t("Also show the Reel in your profile grid")} checked={o.share_to_feed ?? true} onChange={(v) => set({ share_to_feed: v })} />}
                  <label className="block text-sm">{t("Collaborators (up to 3 usernames)")}
                    <input className="input mt-1" value={(o.collaborators ?? []).join(", ")} placeholder="@sita_store, @ram"
                      onChange={(e) => set({ collaborators: e.target.value.split(",").map((x) => x.trim().replace(/^@/, "")).filter(Boolean).slice(0, 3) })} />
                  </label>
                  <label className="block text-sm">{t("First comment")}
                    <textarea className="input mt-1 min-h-[60px]" maxLength={2200} value={o.first_comment ?? ""} placeholder={t("e.g. extra hashtags or how to order")} onChange={(e) => set({ first_comment: e.target.value })} />
                  </label>
                </>
              )}
              {p === "facebook" && (
                <>
                  {isVideo && (
                    <label className="block text-sm">{t("Video title")}
                      <input className="input mt-1" maxLength={255} value={o.title ?? ""} onChange={(e) => set({ title: e.target.value })} />
                    </label>
                  )}
                  <label className="block text-sm">{t("First comment")}
                    <textarea className="input mt-1 min-h-[60px]" maxLength={8000} value={o.first_comment ?? ""} placeholder={t("e.g. a link, phone number or how to order")} onChange={(e) => set({ first_comment: e.target.value })} />
                  </label>
                </>
              )}
              <p className="text-[11px] text-slate-400">{t("These settings are remembered for {name}.", { name: account.name })}</p>
            </div>
          )}

          {p === "tiktok" && (
            <p className="text-[11px] leading-relaxed text-slate-500">
              {o.brand_content
                ? <>{t("By posting, you agree to TikTok's")} <a className="underline" href="https://www.tiktok.com/legal/page/global/bc-policy/en" target="_blank" rel="noopener noreferrer">{t("Branded Content Policy")}</a> {t("and")} <a className="underline" href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank" rel="noopener noreferrer">{t("Music Usage Confirmation")}</a>.</>
                : <>{t("By posting, you agree to TikTok's")} <a className="underline" href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank" rel="noopener noreferrer">{t("Music Usage Confirmation")}</a>.</>}
              {" "}{t("TikTok may take a few minutes to process the video. Until TikTok audits this app, posts are visible only to you.")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
