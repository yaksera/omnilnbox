"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import clsx from "clsx";
import {
  Check, CircleHelp, Gift, Inbox, Languages, LogOut, Megaphone, Menu, PackagePlus, PenSquare, Plus, RadioTower, ShoppingBag, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Me } from "@/lib/types";
import { useLang, useT } from "@/lib/i18n";
import { Api, auth } from "@/lib/api";
import { avatarColor, initials } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/money";

export type NavLink = { href: string; label: string; icon: LucideIcon };

/** Slide-up panel used for "Create" and "More". Tap the backdrop or swipe it down to close. */
export function BottomSheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: string; children: React.ReactNode }) {
  const t = useT();
  const [drag, setDrag] = useState(0);
  const [start, setStart] = useState<number | null>(null);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose]);
  return (
    <div className={clsx("fixed inset-0 z-[60] md:hidden", open ? "pointer-events-auto" : "pointer-events-none")} aria-hidden={!open}>
      <div className={clsx("absolute inset-0 bg-slate-900/40 transition-opacity duration-200", open ? "opacity-100" : "opacity-0")} onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label={title}
        className={clsx("pb-safe absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-3xl bg-white shadow-2xl",
          start === null && "transition-transform duration-300 ease-out")}
        style={{ transform: open ? `translateY(${drag}px)` : "translateY(100%)" }}
        onTouchStart={(e) => setStart(e.touches[0].clientY)}
        onTouchMove={(e) => { if (start !== null) setDrag(Math.max(0, e.touches[0].clientY - start)); }}
        onTouchEnd={() => { if (drag > 90) onClose(); setDrag(0); setStart(null); }}>
        <div className="sticky top-0 z-10 bg-white px-5 pb-2 pt-3">
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-slate-200" />
          {title && (
            <div className="flex items-center justify-between">
              <p className="text-lg font-semibold">{title}</p>
              <button onClick={onClose} className="-mr-2 rounded-full p-2 text-slate-500 active:bg-slate-100" aria-label={t("Close")}><X size={20} /></button>
            </div>
          )}
        </div>
        <div className="px-5 pb-5">{children}</div>
      </div>
    </div>
  );
}

function Tab({ href, label, icon: Icon, active, badge }: { href: string; label: string; icon: LucideIcon; active: boolean; badge?: number }) {
  return (
    <Link href={href} className={clsx("relative flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[11px] font-medium",
      active ? "text-brand-700" : "text-slate-500")}>
      <span className={clsx("flex h-8 w-14 items-center justify-center rounded-full transition", active && "bg-brand-50")}>
        <Icon size={22} strokeWidth={active ? 2.4 : 2} />
      </span>
      {label}
      {!!badge && (
        <span className="absolute left-1/2 top-0.5 ml-2 min-w-[18px] rounded-full bg-red-500 px-1 text-center text-[10px] font-bold leading-[18px] text-white ring-2 ring-white">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </Link>
  );
}

export default function MobileNav({ me, links, unread, onLogout, hidden }: {
  me: Me; links: NavLink[]; unread: number; onLogout: () => void; hidden: boolean;
}) {
  const t = useT();
  const { lang, setLang } = useLang();
  const pathname = usePathname();
  const [sheet, setSheet] = useState<"" | "create" | "more">("");
  useEffect(() => { setSheet(""); }, [pathname]);
  const is = (p: string) => pathname === p || pathname.startsWith(`${p}/`);
  const has = (f: string) => me.workspace.features.includes(f);
  const pinned = ["/inbox", "/orders", "/publish"];
  const moreLinks = links.filter((l) => !pinned.includes(l.href));
  const moreActive = moreLinks.some((l) => is(l.href)) || is("/affiliate");

  const create: Array<{ href: string; label: string; sub: string; icon: LucideIcon; show: boolean }> = [
    { href: "/publish", label: "New post", sub: "Facebook, Instagram, YouTube, TikTok", icon: PenSquare, show: has("social_publishing") },
    { href: "/orders/new", label: "New order", sub: "Take an order from a chat or call", icon: ShoppingBag, show: has("orders") },
    { href: "/products", label: "Add product", sub: "Photo, price and stock", icon: PackagePlus, show: has("orders") },
    { href: "/broadcasts", label: "Broadcast", sub: "Message many customers at once", icon: RadioTower, show: has("broadcasts") },
  ];

  return (
    <>
      <nav className={clsx("pb-safe fixed inset-x-0 bottom-0 z-50 border-t border-slate-200 bg-white/95 backdrop-blur transition-transform duration-200 md:hidden",
        hidden && "pointer-events-none translate-y-[calc(100%+2rem)]")} aria-label={t("Main")}>
        <div className="flex items-end px-1 pt-1">
          <Tab href="/inbox" label={t("Inbox")} icon={Inbox} active={is("/inbox")} badge={unread} />
          <Tab href="/orders" label={t("Orders")} icon={ShoppingBag} active={is("/orders")} />
          <button onClick={() => setSheet("create")} className="flex flex-1 flex-col items-center gap-0.5 pb-1.5 text-[11px] font-medium text-slate-500" aria-label={t("Create")}>
            <span className="-mt-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-brand-600/30 active:scale-95">
              <Plus size={26} strokeWidth={2.4} />
            </span>
            {t("Create")}
          </button>
          <Tab href="/publish" label={t("Publish")} icon={Megaphone} active={is("/publish")} />
          <button onClick={() => setSheet("more")} className={clsx("flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[11px] font-medium", moreActive ? "text-brand-700" : "text-slate-500")}>
            <span className={clsx("flex h-8 w-14 items-center justify-center rounded-full", moreActive && "bg-brand-50")}><Menu size={22} /></span>
            {t("More")}
          </button>
        </div>
      </nav>

      <BottomSheet open={sheet === "create"} onClose={() => setSheet("")} title={t("Create")}>
        <div className="space-y-2">
          {create.filter((c) => c.show).map((c) => (
            <Link key={c.href} href={c.href} className="flex items-center gap-3 rounded-2xl border border-slate-200 p-3 active:bg-slate-50">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-700"><c.icon size={22} /></span>
              <span className="min-w-0 flex-1"><span className="block font-medium">{t(c.label)}</span><span className="block truncate text-sm text-slate-500">{t(c.sub)}</span></span>
            </Link>
          ))}
        </div>
      </BottomSheet>

      <BottomSheet open={sheet === "more"} onClose={() => setSheet("")}>
        <div className="flex items-center gap-3 pb-4">
          <span className="flex h-12 w-12 items-center justify-center rounded-full text-sm font-semibold text-white" style={{ background: avatarColor(me.user.email) }}>{initials(me.user.name)}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{me.user.name}</p>
            <p className="truncate text-sm text-slate-500">{me.workspace.name} · {me.workspace.plan_name}</p>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2">
          {[...moreLinks, { href: "/affiliate", label: "Refer & earn", icon: Gift }].map((l) => (
            <Link key={l.href} href={l.href} className={clsx("flex flex-col items-center gap-1.5 rounded-2xl p-2 text-center text-xs font-medium active:bg-slate-100",
              is(l.href) ? "bg-brand-50 text-brand-700" : "text-slate-700")}>
              <span className={clsx("flex h-11 w-11 items-center justify-center rounded-2xl", is(l.href) ? "bg-white" : "bg-slate-100")}><l.icon size={21} /></span>
              <span className="line-clamp-2">{t(l.label)}</span>
            </Link>
          ))}
          <a href="/docs" target="_blank" rel="noopener" className="flex flex-col items-center gap-1.5 rounded-2xl p-2 text-center text-xs font-medium text-slate-700 active:bg-slate-100">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100"><CircleHelp size={21} /></span>{t("Help")}
          </a>
        </div>

        {me.memberships.length > 1 && (
          <div className="mt-5">
            <p className="pb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{t("Workspaces")}</p>
            <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200">
              {me.memberships.map((m) => (
                <button key={m.workspace.id} className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-slate-50"
                  // full reload so every page re-fetches data for the new workspace
                  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
                  onClick={() => { auth.setWorkspace(m.workspace.id); window.location.assign("/inbox"); }}>
                  <span className="min-w-0 flex-1"><span className="block truncate font-medium">{m.workspace.name}</span>
                    <span className="text-xs text-slate-500">{ROLE_LABELS[m.role]} · {m.workspace.plan_name}</span></span>
                  {m.workspace.id === me.workspace.id && <Check size={18} className="text-brand-600" />}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-5 flex items-center justify-between rounded-2xl border border-slate-200 px-4 py-3">
          <span className="flex items-center gap-2 text-sm text-slate-700"><Languages size={18} /> {t("Language")}</span>
          <span className="flex rounded-xl bg-slate-100 p-0.5 text-sm">
            {(["en", "ne"] as const).map((l) => (
              <button key={l} type="button" onClick={() => { setLang(l); Api.setLanguage(l).catch(() => undefined); }}
                className={clsx("rounded-lg px-3 py-1.5 font-medium", lang === l ? "bg-white shadow-sm" : "text-slate-500")}>{l === "en" ? "English" : "नेपाली"}</button>
            ))}
          </span>
        </div>
        <button onClick={onLogout} className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl border border-red-100 py-3 text-sm font-medium text-red-600 active:bg-red-50">
          <LogOut size={18} /> {t("Log out")}
        </button>
      </BottomSheet>
    </>
  );
}
