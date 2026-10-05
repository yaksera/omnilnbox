import type { ComponentType } from "react";
import clsx from "clsx";
import { AtSign, Globe } from "lucide-react";
import {
  SiDiscord, SiFacebook, SiGmail, SiInstagram, SiMessenger, SiTelegram, SiTiktok, SiViber, SiWhatsapp, SiYoutube, SiZoho,
} from "react-icons/si";
import { PiMicrosoftOutlookLogoFill } from "react-icons/pi";

type IconType = ComponentType<{ size?: number; className?: string }>;

// Official platform marks (from the Simple Icons / Phosphor sets via react-icons) on each brand's colour,
// so agents can see at a glance where every message came from.
export const PROVIDER_UI: Record<string, { label: string; color: string; icon: IconType }> = {
  whatsapp: { label: "WhatsApp", color: "#25D366", icon: SiWhatsapp },
  instagram: { label: "Instagram", color: "#E4405F", icon: SiInstagram },
  messenger: { label: "Messenger", color: "#0866FF", icon: SiMessenger },
  tiktok: { label: "TikTok", color: "#000000", icon: SiTiktok },
  telegram: { label: "Telegram", color: "#26A5E4", icon: SiTelegram },
  viber: { label: "Viber", color: "#7360F2", icon: SiViber },
  website: { label: "Website chat", color: "#0F766E", icon: Globe as IconType },
  discord: { label: "Discord", color: "#5865F2", icon: SiDiscord },
  gmail: { label: "Gmail", color: "#EA4335", icon: SiGmail },
  outlook: { label: "Outlook", color: "#0078D4", icon: PiMicrosoftOutlookLogoFill },
  zoho: { label: "Zoho Mail", color: "#E42527", icon: SiZoho },
  imap: { label: "Email", color: "#0EA5E9", icon: AtSign as IconType },
  // publishing destinations
  facebook: { label: "Facebook", color: "#0866FF", icon: SiFacebook },
  youtube: { label: "YouTube", color: "#FF0000", icon: SiYoutube },
};

export const PUBLISH_PLATFORMS = ["facebook", "instagram", "youtube", "tiktok"] as const;

export const PROVIDER_ORDER = ["whatsapp", "instagram", "messenger", "tiktok", "viber", "telegram", "website", "discord", "gmail", "outlook", "zoho", "imap"];
export const EMAIL_PROVIDERS = ["gmail", "outlook", "zoho", "imap"];

export function providerUI(key: string) {
  return PROVIDER_UI[key] ?? { label: key, color: "#64748b", icon: AtSign as IconType };
}

const BOX = { xs: "h-4 w-4 rounded-[5px]", sm: "h-6 w-6 rounded-md", md: "h-8 w-8 rounded-lg", lg: "h-11 w-11 rounded-xl", xl: "h-14 w-14 rounded-2xl" };
const GLYPH = { xs: 10, sm: 14, md: 17, lg: 23, xl: 30 };

/** Brand symbol on its brand colour. */
export function ProviderIcon({ provider, size = "md", className }: {
  provider: string; size?: keyof typeof BOX; className?: string;
}) {
  const ui = providerUI(provider);
  const Icon = ui.icon;
  return (
    <span
      className={clsx("inline-flex shrink-0 items-center justify-center text-white", BOX[size], className)}
      style={{ background: ui.color }}
      title={ui.label}
      aria-label={ui.label}
      role="img"
    >
      <Icon size={GLYPH[size]} />
    </span>
  );
}

/** "via WhatsApp" pill used on messages and headers. */
export function ProviderBadge({ provider, className }: { provider: string; className?: string }) {
  const ui = providerUI(provider);
  const Icon = ui.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium", className)}
      style={{ background: `${ui.color}14`, color: ui.color === "#000000" ? "#111827" : ui.color }}>
      <Icon size={10} /> {ui.label}
    </span>
  );
}
