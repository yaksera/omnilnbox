import type { MediaAsset, PublishConfig, PublishOptions, PublishPlatform, TikTokCreator } from "@/lib/types";

export type TargetState = { custom: boolean; caption: string; opts: PublishOptions };
export type Tr = (s: string, v?: Record<string, string | number>) => string;

/** Settings worth remembering per account (not the text of one post). */
const REMEMBER: Array<keyof PublishOptions> = ["privacy", "category_id", "made_for_kids", "notify_subscribers",
  "disable_comment", "disable_duet", "disable_stitch", "share_to_feed"];

export function defaultOpts(platform: PublishPlatform): PublishOptions {
  if (platform === "youtube") return { title: "", privacy: "public", tags: [], category_id: "22", made_for_kids: false, notify_subscribers: true };
  // TikTok: no default privacy (TikTok requires the person posting to choose)
  if (platform === "tiktok") return { privacy: "", disable_comment: false, disable_duet: false, disable_stitch: false, brand_organic: false, brand_content: false };
  if (platform === "instagram") return { share_to_feed: true, collaborators: [], first_comment: "" };
  return { title: "", first_comment: "" };
}

const KEY = (id: string) => `omni.publishDefaults.${id}`;
export function loadRemembered(accountId: string): PublishOptions {
  try {
    const raw = window.localStorage.getItem(KEY(accountId));
    return raw ? (JSON.parse(raw) as PublishOptions) : {};
  } catch { return {}; }
}
export function remember(accountId: string, opts: PublishOptions) {
  try {
    const keep = Object.fromEntries(REMEMBER.filter((k) => opts[k] !== undefined && opts[k] !== "").map((k) => [k, opts[k]]));
    window.localStorage.setItem(KEY(accountId), JSON.stringify(keep));
  } catch { /* storage unavailable */ }
}

export function fmtDuration(s?: number | null) {
  if (!s && s !== 0) return "";
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
export function shape(media: MediaAsset | null): "vertical" | "horizontal" | "square" | "" {
  if (!media?.width || !media?.height) return "";
  const r = media.width / media.height;
  return r < 0.9 ? "vertical" : r > 1.1 ? "horizontal" : "square";
}

/** Problems that block publishing (mirrors the server's checks). */
export function blockers(platform: PublishPlatform, cfg: PublishConfig, caption: string, media: MediaAsset | null, ts: TargetState,
  tr: Tr, creator?: TikTokCreator | null): string[] {
  const r = cfg.limits[platform], out: string[] = [], o = ts.opts;
  if (caption.length > r.caption) out.push(tr("Text {len}/{max}", { len: caption.length, max: r.caption }));
  if (r.needs_media && !media) out.push(r.video_only ? tr("Needs a video") : tr("Needs an image or video"));
  if (media && r.video_only && media.kind !== "video") out.push(tr("Video only"));
  if (media && r.jpeg_only && media.kind === "image" && media.mime !== "image/jpeg") out.push(tr("JPEG images only"));
  const d = media?.kind === "video" ? media.duration ?? 0 : 0;
  if (platform === "youtube") {
    if (!o.title?.trim()) out.push(tr("Add a title"));
    if (/[<>]/.test(o.title ?? "")) out.push(tr("No < or > in the title"));
    if ((o.tags ?? []).join(",").length > 500) out.push(tr("Tags too long"));
  }
  if (platform === "tiktok") {
    if (!o.privacy) out.push(tr("Choose who can see it"));
    if (o.brand_content && o.privacy === "SELF_ONLY") out.push(tr("Branded content can't be private"));
    const max = creator?.max_seconds ?? 600;
    if (d && d > max) out.push(tr("Max {m} min on this account", { m: Math.floor(max / 60) }));
  }
  if (platform === "instagram" && d && (d < 3 || d > 900)) out.push(tr("Reels must be 3 s – 15 min"));
  if (platform === "facebook" && !caption.trim() && !media) out.push(tr("Add text or media"));
  return out;
}

/** Helpful hints that don't block publishing. */
export function hints(platform: PublishPlatform, media: MediaAsset | null, tr: Tr): string[] {
  const s = shape(media), d = media?.duration ?? 0, out: string[] = [];
  if (media?.kind !== "video") return out;
  if ((platform === "tiktok" || platform === "instagram") && s === "horizontal") out.push(tr("Horizontal video looks small here. Vertical 9:16 works best."));
  if (platform === "youtube" && s === "vertical" && d && d <= 180) out.push(tr("Vertical and under 3 minutes: YouTube shows it as a Short."));
  if (platform === "youtube" && d > 900) out.push(tr("Over 15 minutes needs a verified YouTube channel."));
  return out;
}

export const TIKTOK_PRIVACY: Record<string, string> = {
  PUBLIC_TO_EVERYONE: "Everyone", MUTUAL_FOLLOW_FRIENDS: "Friends", FOLLOWER_OF_CREATOR: "Followers", SELF_ONLY: "Only me",
};
