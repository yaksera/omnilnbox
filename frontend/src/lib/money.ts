export type Currency = "NPR" | "USD";

export function money(amount: number | string, currency: Currency, opts: { compact?: boolean } = {}) {
  const n = Number(amount);
  if (currency === "NPR") {
    return `Rs. ${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  }
  // "compact" drops ".00" on whole numbers; otherwise always show cents ($9.60, not $9.6)
  const whole = Number.isInteger(n);
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: whole && opts.compact ? 0 : 2, maximumFractionDigits: 2 })}`;
}

export const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  supervisor: "Supervisor",
  agent: "Agent",
};

export const ROLE_HELP: Record<string, string> = {
  owner: "Everything, including billing and ownership.",
  admin: "Channels, team, settings and all conversations. No billing.",
  supervisor: "All conversations, assigning, saved replies, tags and analytics.",
  agent: "Replies to conversations. Can take or release conversations.",
};

export function daysLeft(iso: string | null) {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000));
}
