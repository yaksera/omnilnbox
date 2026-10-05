import Link from "next/link";
import clsx from "clsx";
import { Inbox } from "lucide-react";

export default function Logo({ dark = false, href = "/", className }: { dark?: boolean; href?: string; className?: string }) {
  return (
    <Link href={href} className={clsx("flex items-center gap-2 font-semibold tracking-tight", dark ? "text-white" : "text-slate-900", className)}>
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm">
        <Inbox size={17} strokeWidth={2.4} />
      </span>
      OmniInbox
    </Link>
  );
}
