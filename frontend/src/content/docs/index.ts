import type { Block, Doc } from "./types";
import { START } from "./start";
import { CHANNELS } from "./channels";
import { AI } from "./ai";
import { SELLING } from "./selling";
import { GROW } from "./grow";
import { ACCOUNT } from "./account";

export type { Block, Doc };

export const DOCS: Doc[] = [...START, ...CHANNELS, ...AI, ...SELLING, ...GROW, ...ACCOUNT];

export const CATEGORIES = [
  { name: "Getting started", blurb: "Sign up, the inbox, your team and notifications." },
  { name: "Channels", blurb: "Connect WhatsApp, Instagram, Messenger, Viber, TikTok and more." },
  { name: "AI & automation", blurb: "AI chatbot, knowledge base and auto-replies." },
  { name: "Selling", blurb: "Products, orders, Khalti/eSewa payments and couriers." },
  { name: "Marketing", blurb: "Social publishing and broadcasts." },
  { name: "Reports", blurb: "Analytics, reply-time targets and satisfaction." },
  { name: "Account", blurb: "Billing, security, activity log and branding." },
  { name: "Developers", blurb: "REST API and webhooks." },
  { name: "Help", blurb: "Fixes for common problems." },
] as const;

export function getDoc(slug: string) {
  return DOCS.find((d) => d.slug === slug);
}

export function byCategory(name: string) {
  return DOCS.filter((d) => d.category === name);
}

/** Plain text of a doc, for search. */
export function docText(d: Doc) {
  const parts: string[] = [d.title, d.summary];
  for (const b of d.body) {
    if ("p" in b) parts.push(b.p);
    else if ("h" in b) parts.push(b.h);
    else if ("steps" in b) parts.push(...b.steps);
    else if ("list" in b) parts.push(...b.list);
    else if ("tip" in b) parts.push(b.tip);
    else if ("warn" in b) parts.push(b.warn);
    else if ("table" in b) parts.push(...b.table.rows.flat());
  }
  return parts.join(" ").replace(/\*\*|`|\[|\]\([^)]*\)/g, " ").replace(/\s+/g, " ");
}
