"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import {
  ArrowLeft, Bot, Check, ShoppingBag, CircleAlert, Inbox as InboxIcon, LoaderCircle, Plug, RefreshCw, Search, Send, Sparkles, StickyNote,
  Tag as TagIcon, UserCheck, X,
} from "lucide-react";
import { Api, ApiError } from "@/lib/api";
import type { CannedReply, Channel, Conversation, KnowledgeRef, Member, Message, Stats, Tag } from "@/lib/types";
import { EMAIL_PROVIDERS, PROVIDER_ORDER, ProviderBadge, ProviderIcon, providerUI } from "@/lib/providers";
import { avatarColor, clockTime, initials, timeAgo } from "@/lib/format";
import { useMe, useMobileChrome } from "@/components/AppShell";
import MobileConversationList, { type MobileFilter } from "@/components/inbox/MobileConversationList";
import { useIsMobile } from "@/lib/useIsMobile";
import { BotChip, RewriteMenu, SourcesLine, SuggestButton, SummaryCard } from "@/components/inbox/AIAssist";
import CustomerPanel from "@/components/commerce/CustomerPanel";
import PaymentChecks from "@/components/inbox/PaymentChecks";
import AIReportCard from "@/components/ai/AIReportCard";
import { AttachButton, MAX_FILE_MB, MessageFiles, PendingFiles, VoiceRecorder, type PendingFile } from "@/components/inbox/Attachments";
import { useLiveUpdates } from "@/lib/realtime";
import { useT } from "@/lib/i18n";

type View = { kind: "all" } | { kind: "unread" } | { kind: "mine" } | { kind: "unassigned" }
  | { kind: "provider"; provider: string } | { kind: "email" } | { kind: "tag"; tag: number };

const STATUS_LABELS: Record<string, string> = { open: "Open", pending: "Pending", closed: "Closed", all: "All" };

const FALLBACK_POLL_MS = 60000;  // instant updates come from useLiveUpdates; this is only a safety net

function Avatar({ name, url, size = 40 }: { name: string; url?: string; size?: number }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className="shrink-0 rounded-full object-cover" style={{ width: size, height: size }} />;
  }
  return (
    <span className="flex shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
      style={{ width: size, height: size, background: avatarColor(name) }}>
      {initials(name)}
    </span>
  );
}

function TagChip({ tag, onRemove }: { tag: Tag; onRemove?: () => void }) {
  const t = useT();
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold text-white" style={{ background: tag.color }}>
      {tag.name}
      {onRemove && <button onClick={onRemove} aria-label={t("Remove {name}", { name: tag.name })} className="hover:opacity-70"><X size={10} /></button>}
    </span>
  );
}

export default function InboxPage() {
  const t = useT();
  const { me } = useMe();
  const [view, setView] = useState<View>({ kind: "all" });
  const [status, setStatus] = useState("open");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [channels, setChannels] = useState<Channel[] | null>(null);
  const [tags, setTags] = useState<Tag[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [canned, setCanned] = useState<CannedReply[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);
  // Phone layout: Messages / Comments tabs and quick-filter chips instead of the folder sidebar
  const isMobile = useIsMobile();
  const [mobileTab, setMobileTab] = useState<"message" | "comment">("message");
  const [mobileFilter, setMobileFilter] = useState<MobileFilter>({ kind: "all" });
  const { setTabBarHidden } = useMobileChrome();
  useEffect(() => {
    setTabBarHidden(isMobile && !!selectedId);  // full-screen chat on phones: the reply box needs the room
    return () => setTabBarHidden(false);
  }, [isMobile, selectedId, setTabBarHidden]);
  // Phone back button / back swipe closes the open chat instead of leaving the inbox
  const pushedChat = useRef(false);
  useEffect(() => {
    const onPop = () => { if (pushedChat.current) { pushedChat.current = false; setSelectedId(null); } };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  function openConversation(id: string) {
    if (isMobile && !pushedChat.current) { window.history.pushState({ chat: id }, ""); pushedChat.current = true; }
    setSelectedId(id);
  }
  function closeConversation() {
    if (pushedChat.current) window.history.back();  // popstate clears the selection
    else setSelectedId(null);
  }

  useEffect(() => {
    // /inbox?c=<conversation id> (from a push notification or a link) opens that conversation
    const c = new URLSearchParams(window.location.search).get("c");
    if (c) { setStatus("all"); setSelectedId(c); }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  const params = useMemo(() => {
    const p: Record<string, string> = { status, q: debounced, limit: "100" };
    if (isMobile) {
      p.kind = mobileTab;
      const f = mobileFilter;
      if (f.kind === "unread") p.unread = "1";
      if (f.kind === "handoff") p.ai = "handoff";
      if (f.kind === "mine") p.assigned = "me";
      if (f.kind === "provider") p.provider = f.provider;
      if (f.kind === "tag") p.tag = String(f.tag);
      return p;
    }
    if (view.kind === "unread") p.unread = "1";
    if (view.kind === "mine") p.assigned = "me";
    if (view.kind === "unassigned") p.assigned = "unassigned";
    if (view.kind === "provider") p.provider = view.provider;
    if (view.kind === "email") p.category = "email";
    if (view.kind === "tag") p.tag = String(view.tag);
    return p;
  }, [view, status, debounced, isMobile, mobileTab, mobileFilter]);

  const loadList = useCallback(async () => {
    const [list, s] = await Promise.all([Api.conversations(params), Api.stats()]);
    setConversations(list.results);
    setStats(s);
  }, [params]);

  useEffect(() => {
    Api.channels().then(setChannels).catch(() => setChannels([]));
    Api.tags().then(setTags).catch(() => undefined);
    Api.team().then((t) => setMembers(t.members)).catch(() => undefined);
    Api.canned().then(setCanned).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadList().catch(() => undefined);
    const t = setInterval(() => {
      if (document.visibilityState === "visible") loadList().catch(() => undefined);
    }, FALLBACK_POLL_MS);
    return () => clearInterval(t);
  }, [loadList]);
  useLiveUpdates(() => { loadList().catch(() => undefined); });

  const selected = conversations?.find((c) => c.id === selectedId) ?? null;
  const connectedProviders = useMemo(() => {
    const keys = new Set((channels ?? []).map((c) => c.provider));
    return PROVIDER_ORDER.filter((p) => keys.has(p));
  }, [channels]);

  async function loadDemo() {
    setLoadingDemo(true);
    try {
      await Api.loadDemo();
      setChannels(await Api.channels());
      await loadList();
    } finally {
      setLoadingDemo(false);
    }
  }

  function onConversationChanged(conv: Conversation) {
    setConversations((list) => list?.map((c) => (c.id === conv.id ? conv : c)) ?? null);
    loadList().catch(() => undefined);
  }

  if (channels && channels.length === 0) {
    const canSetup = me.capabilities.includes("manage_channels");
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="card max-w-lg p-8 text-center">
          <div className="flex justify-center -space-x-2">
            {PROVIDER_ORDER.slice(0, 6).map((p) => <ProviderIcon key={p} provider={p} size="lg" className="ring-4 ring-white" />)}
          </div>
          <h2 className="mt-5 text-lg font-semibold">{t("Connect your first channel")}</h2>
          <p className="mt-2 text-sm text-slate-600">
            {canSetup
              ? t("Bring in WhatsApp, Instagram, Messenger, TikTok, Telegram, Discord, Gmail, Outlook or Zoho Mail, or load sample conversations to explore first.")
              : t("No channels are connected yet. Ask an admin to connect your team's channels.")}
          </p>
          {canSetup && (
            <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
              <Link href="/channels" className="btn-primary"><Plug size={16} /> {t("Connect a channel")}</Link>
              <button onClick={loadDemo} className="btn-secondary" disabled={loadingDemo}>
                {loadingDemo ? <LoaderCircle className="animate-spin" size={16} /> : <Sparkles size={16} />} {t("Load demo data")}
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  const isActive = (v: View) => JSON.stringify(v) === JSON.stringify(view);
  const navItem = (v: View, label: string, count: number | undefined, icon: React.ReactNode) => (
    <button key={label} onClick={() => setView(v)}
      className={clsx("flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-sm transition",
        isActive(v) ? "bg-brand-50 font-medium text-brand-700" : "text-slate-700 hover:bg-slate-100")}>
      {icon}
      <span className="flex-1 truncate">{label}</span>
      {!!count && <span className="rounded-full bg-brand-600 px-1.5 text-[11px] font-semibold text-white">{count}</span>}
    </button>
  );

  return (
    <div className="flex h-full min-h-0">
      {/* Folders */}
      <div className="hidden w-56 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="border-b border-slate-100 px-4 py-4">
          <p className="text-xs uppercase tracking-wide text-slate-400">{t("Workspace")}</p>
          <p className="truncate font-semibold">{me.workspace.name}</p>
        </div>
        <div className="scroll-thin flex-1 space-y-0.5 overflow-y-auto p-2">
          {navItem({ kind: "all" }, t("All conversations"), undefined, <InboxIcon size={16} />)}
          {navItem({ kind: "unread" }, t("Unread"), stats?.unread_conversations, <CircleAlert size={16} />)}
          {navItem({ kind: "mine" }, t("Assigned to me"), stats?.assigned_to_me, <UserCheck size={16} />)}
          {navItem({ kind: "unassigned" }, t("Unassigned"), undefined, <InboxIcon size={16} className="opacity-60" />)}
          <p className="px-2.5 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-slate-400">{t("Channels")}</p>
          {connectedProviders.map((p) =>
            navItem({ kind: "provider", provider: p }, providerUI(p).label, stats?.by_provider[p]?.unread, <ProviderIcon provider={p} size="xs" />))}
          {connectedProviders.some((p) => EMAIL_PROVIDERS.includes(p)) &&
            navItem({ kind: "email" }, t("All email"), undefined, <ProviderIcon provider="imap" size="xs" />)}
          {tags.length > 0 && <p className="px-2.5 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-slate-400">{t("Tags")}</p>}
          {tags.map((tg) => navItem({ kind: "tag", tag: tg.id }, tg.name, undefined, <span className="h-3 w-3 rounded-full" style={{ background: tg.color }} />))}
          {me.capabilities.includes("manage_channels") && (
            <Link href="/channels" className="mt-2 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm text-slate-500 hover:bg-slate-100">
              <Plug size={16} /> {t("Manage channels")}
            </Link>
          )}
        </div>
      </div>

      {isMobile && !selectedId && (
        <MobileConversationList me={me} conversations={conversations} stats={stats} providers={connectedProviders} tags={tags} now={now}
          tab={mobileTab} setTab={(k) => { setMobileTab(k); setConversations(null); }}
          filter={mobileFilter} setFilter={(f) => { setMobileFilter(f); setConversations(null); }}
          status={status} setStatus={setStatus} query={query} setQuery={setQuery}
          onOpen={openConversation} onRefresh={loadList}
          onUpdate={(c, body) => { Api.updateConversation(c.id, body).then(onConversationChanged).catch(() => undefined); }} />
      )}

      {/* Conversation list */}
      {!isMobile && <div className={clsx("min-h-0 w-full shrink-0 flex-col border-r border-slate-200 bg-white md:flex md:w-80", selectedId ? "hidden" : "flex")}>
        <div className="space-y-3 border-b border-slate-100 p-3">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
            <input className="input pl-9" placeholder={t("Search name, handle, message…")} value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm">
            {["open", "pending", "closed", "all"].map((s) => (
              <button key={s} onClick={() => setStatus(s)}
                className={clsx("flex-1 rounded-md py-1 capitalize", status === s ? "bg-white font-medium shadow-sm" : "text-slate-500")}>{t(STATUS_LABELS[s])}</button>
            ))}
          </div>
          <select className="input lg:hidden" value={view.kind === "provider" ? view.provider : view.kind === "tag" ? `tag:${view.tag}` : view.kind}
            onChange={(e) => {
              const v = e.target.value;
              if (["all", "unread", "mine", "unassigned", "email"].includes(v)) setView({ kind: v } as View);
              else if (v.startsWith("tag:")) setView({ kind: "tag", tag: Number(v.slice(4)) });
              else setView({ kind: "provider", provider: v });
            }}>
            <option value="all">{t("All conversations")}</option>
            <option value="unread">{t("Unread")}</option>
            <option value="mine">{t("Assigned to me")}</option>
            <option value="unassigned">{t("Unassigned")}</option>
            {connectedProviders.map((p) => <option key={p} value={p}>{providerUI(p).label}</option>)}
            {tags.map((tg) => <option key={tg.id} value={`tag:${tg.id}`}>#{tg.name}</option>)}
          </select>
        </div>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {me.workspace.features.includes("ai_chatbot") && <AIReportCard compact />}
          {conversations === null && <div className="flex justify-center p-8 text-slate-400"><LoaderCircle className="animate-spin" /></div>}
          {conversations?.length === 0 && <p className="p-8 text-center text-sm text-slate-500">{t("No conversations here.")}</p>}
          {conversations?.map((c) => {
            const name = c.contact.name || c.contact.handle || t("Unknown");
            const waitMin = c.unread_count > 0 && c.status !== "closed" && c.last_message_at ? (now - new Date(c.last_message_at).getTime()) / 60000 : 0;
            const overdue = me.workspace.sla_minutes > 0 && waitMin > me.workspace.sla_minutes;
            return (
              <button key={c.id} onClick={() => openConversation(c.id)}
                className={clsx("flex w-full gap-3 border-b border-slate-100 px-3 py-3 text-left transition",
                  c.id === selectedId ? "bg-brand-50" : "hover:bg-slate-50")}>
                <div className="relative">
                  <Avatar name={name} url={c.contact.avatar_url} />
                  <ProviderIcon provider={c.channel.provider} size="xs" className="absolute -bottom-0.5 -right-0.5 ring-2 ring-white" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className={clsx("truncate text-sm", c.unread_count ? "font-semibold" : "font-medium")}>{name}</span>
                    <span className={clsx("shrink-0 text-xs", overdue ? "rounded bg-red-50 px-1 font-medium text-red-600" : "text-slate-400")}
                      title={overdue ? t("Waiting longer than your {n}-minute reply target", { n: me.workspace.sla_minutes }) : undefined}>
                      {overdue && "⏱ "}{timeAgo(c.last_message_at)}
                    </span>
                  </div>
                  {c.subject && <p className="truncate text-xs font-medium text-slate-700">{c.subject}</p>}
                  <div className="flex items-center gap-2">
                    <p className={clsx("flex-1 truncate text-sm", c.unread_count ? "text-slate-800" : "text-slate-500")}>{c.last_message_preview}</p>
                    {c.unread_count > 0 && c.id !== selectedId && <span className="rounded-full bg-brand-600 px-1.5 text-[11px] font-semibold text-white">{c.unread_count}</span>}
                  </div>
                  {(c.tags.length > 0 || c.assigned_to) && (
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      {c.tags.slice(0, 3).map((tg) => <TagChip key={tg.id} tag={tg} />)}
                      {c.assigned_to && (
                        <span className="ml-auto flex items-center gap-1 text-[10px] text-slate-500" title={t("Assigned to {name}", { name: c.assigned_to.name })}>
                          <span className="flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-bold text-white" style={{ background: avatarColor(c.assigned_to.email) }}>{initials(c.assigned_to.name)}</span>
                          {c.assigned_to.id === me.user.id ? t("You") : c.assigned_to.name.split(" ")[0]}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>}

      {/* Thread */}
      <div className={clsx("min-h-0 min-w-0 flex-1 bg-slate-50 md:flex", selectedId ? "flex" : "hidden")}>
        {selected ? (
          <Thread key={selected.id} conversation={selected} tags={tags} members={members} canned={canned}
            onBack={closeConversation} onChanged={onConversationChanged} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center text-slate-400">
            <InboxIcon size={40} />
            <p className="mt-3 text-sm">{t("Select a conversation")}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Thread({ conversation, tags, members, canned, onBack, onChanged }: {
  conversation: Conversation; tags: Tag[]; members: Member[]; canned: CannedReply[];
  onBack: () => void; onChanged: (c: Conversation) => void;
}) {
  const t = useT();
  const { me, can, hasFeature } = useMe();
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"reply" | "note">("reply");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [tagMenu, setTagMenu] = useState(false);
  const [cannedIdx, setCannedIdx] = useState(0);
  const [aiHint, setAiHint] = useState("");
  const [draftSources, setDraftSources] = useState<KnowledgeRef[]>([]);
  const [files, setFiles] = useState<PendingFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const touchKeyboard = useIsMobile();
  const canAttach = !!conversation.channel.can_send_media && conversation.kind !== "comment";
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileSeq = useRef(0);
  const lastCount = useRef(0);
  const newest = useRef<string | undefined>(undefined);
  const provider = conversation.channel.provider;
  const ui = providerUI(provider);
  const isEmail = EMAIL_PROVIDERS.includes(provider);
  const name = conversation.contact.name || conversation.contact.handle || t("Unknown");
  const isComment = conversation.kind === "comment";

  const load = useCallback(async () => {
    const msgs = await Api.messages(conversation.id);
    newest.current = msgs.reduce<string | undefined>((max, m) => (!max || m.created_at > max ? m.created_at : max), undefined);
    setMessages(msgs);
  }, [conversation.id]);

  const poll = useCallback(async () => {
    if (!newest.current) return load();
    const fresh = await Api.messages(conversation.id, newest.current);
    if (!fresh.length) return;
    for (const m of fresh) if (m.created_at > newest.current) newest.current = m.created_at;
    setMessages((prev) => {
      const seen = new Set((prev ?? []).map((m) => m.id));
      return [...(prev ?? []), ...fresh.filter((m) => !seen.has(m.id))];
    });
  }, [conversation.id, load]);

  useEffect(() => {
    load().catch(() => undefined);
    const t = setInterval(() => {
      if (document.visibilityState === "visible") poll().catch(() => undefined);
    }, FALLBACK_POLL_MS);
    return () => clearInterval(t);
  }, [load, poll]);
  const hasPendingFiles = !!messages?.some((m) => m.attachments?.some((a) => a.status === "pending"));
  useLiveUpdates(() => {
    // a file finishing its download changes an existing message, so reload everything in that case
    (hasPendingFiles ? load() : poll()).catch(() => undefined);
  });

  useEffect(() => {
    if (messages && messages.length !== lastCount.current) {
      lastCount.current = messages.length;
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      if (conversation.unread_count || messages[messages.length - 1]?.direction === "in") {
        Api.markRead(conversation.id).then(() => onChanged({ ...conversation, unread_count: 0 })).catch(() => undefined);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, conversation.id, conversation.unread_count]);

  // "/" saved replies
  const slash = text.startsWith("/") && !text.includes(" ") && mode === "reply" ? text.slice(1).toLowerCase() : null;
  const suggestions = slash !== null ? canned.filter((c) => c.shortcut.includes(slash) || c.title.toLowerCase().includes(slash)).slice(0, 6) : [];

  function upload(blob: Blob, name: string, kind = "") {
    const key = `file-${++fileSeq.current}`;
    if (blob.size > MAX_FILE_MB * 1024 * 1024) {
      setFiles((f) => [...f, { key, name, kind, progress: 0, error: t("Larger than {n} MB", { n: MAX_FILE_MB }) }]);
      return;
    }
    const preview = blob.type.startsWith("image/") ? URL.createObjectURL(blob) : undefined;
    setFiles((f) => [...f, { key, name, kind: kind || (blob.type.startsWith("image/") ? "image" : "file"), progress: 0, preview }]);
    Api.uploadAttachment(blob, name, kind, (pct) => setFiles((f) => f.map((x) => (x.key === key ? { ...x, progress: pct } : x))))
      .then((att) => setFiles((f) => f.map((x) => (x.key === key ? { ...x, att, progress: 100 } : x))))
      .catch((err) => setFiles((f) => f.map((x) => (x.key === key ? { ...x, error: err instanceof Error ? err.message : t("Upload failed") } : x))));
  }

  function addFiles(list: File[]) {
    if (!canAttach) { setError(t("{platform} doesn't support sending files from OmniInbox.", { platform: ui.label })); return; }
    setMode("reply");
    list.slice(0, 10 - files.length).forEach((f) => upload(f, f.name));
  }

  function removeFile(key: string) {
    setFiles((f) => {
      const gone = f.find((x) => x.key === key);
      if (gone?.preview) URL.revokeObjectURL(gone.preview);
      return f.filter((x) => x.key !== key);
    });
  }

  const readyFiles = files.filter((f) => f.att && !f.error);
  const uploading = files.some((f) => !f.att && !f.error);

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const body = text.trim();
    if ((!body && !readyFiles.length) || sending || uploading) return;
    setSending(true);
    setError("");
    try {
      await Api.send(conversation.id, body, mode === "note", mode === "note" ? [] : readyFiles.map((f) => f.att!.id));
      setText("");
      setAiHint("");
      setDraftSources([]);
      files.forEach((f) => f.preview && URL.revokeObjectURL(f.preview));
      setFiles([]);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 402 ? t("Internal notes are available on Pro and higher.") : err instanceof Error ? err.message : t("Failed to send"));
    } finally {
      setSending(false);
      await load();
      // the reply pauses the AI assistant in this conversation, so refresh the conversation too
      Api.conversation(conversation.id).then(onChanged).catch(() => onChanged({ ...conversation, unread_count: 0 }));
    }
  }

  async function update(body: { status?: string; assigned_to_id?: number | null; tag_ids?: number[] }) {
    setError("");
    try {
      onChanged(await Api.updateConversation(conversation.id, body));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Update failed"));
    }
  }

  const assignable = can("assign_others") ? members : members.filter((m) => m.id === me.user.id);
  const tagIds = conversation.tags.map((t) => t.id);

  return (
    <div className="flex min-w-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-slate-200 bg-white px-4 py-3">
          <button onClick={onBack} className="btn-ghost -ml-2 px-2 md:hidden" aria-label={t("Back")}><ArrowLeft size={18} /></button>
          <div className="relative">
            <Avatar name={name} url={conversation.contact.avatar_url} size={38} />
            <ProviderIcon provider={provider} size="xs" className="absolute -bottom-0.5 -right-0.5 ring-2 ring-white" />
          </div>
          <div className="min-w-[150px] flex-1">
            <p className="truncate font-semibold">{name}</p>
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
              <ProviderBadge provider={provider} />
              {conversation.contact.handle && conversation.contact.handle !== name && <span className="truncate">{conversation.contact.handle}</span>}
              {conversation.channel.is_demo && <span className="rounded bg-amber-100 px-1 text-amber-700">{t("demo")}</span>}
              {isComment && <span className="rounded bg-sky-100 px-1 font-medium text-sky-800">{t("Public comment")}</span>}
            </div>
          </div>
          <select className="input hidden w-36 py-1.5 text-sm sm:block" aria-label={t("Assign conversation")}
            value={conversation.assigned_to?.id ?? ""}
            onChange={(e) => update({ assigned_to_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">{t("Unassigned")}</option>
            {conversation.assigned_to && !assignable.some((m) => m.id === conversation.assigned_to!.id) && (
              <option value={conversation.assigned_to.id}>{conversation.assigned_to.name}</option>
            )}
            {assignable.map((m) => <option key={m.id} value={m.id}>{m.id === me.user.id ? t("{name} (me)", { name: m.name }) : m.name}</option>)}
          </select>
          {hasFeature("orders") && (
            <Link href={`/orders/new?conversation=${conversation.id}`} className="btn-secondary px-2.5 xl:hidden" title={t("Create order from this chat")}><ShoppingBag size={16} /></Link>
          )}
          {conversation.status === "closed" ? (
            <button onClick={() => update({ status: "open" })} className="btn-secondary px-2.5"><RefreshCw size={16} /> <span className="hidden sm:inline">{t("Reopen")}</span></button>
          ) : (
            <button onClick={() => update({ status: "closed" })} className="btn-primary px-2.5"><Check size={16} /> <span className="hidden sm:inline">{t("Close")}</span></button>
          )}
        </header>

        <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-200 bg-white px-4 py-2">
          {conversation.subject && <span className="mr-2 truncate text-sm font-medium text-slate-700">{conversation.subject}</span>}
          {conversation.tags.map((tg) => (
            <TagChip key={tg.id} tag={tg} onRemove={hasFeature("tags") ? () => update({ tag_ids: tagIds.filter((id) => id !== tg.id) }) : undefined} />
          ))}
          {hasFeature("ai_chatbot") && <BotChip conversation={conversation} onChanged={onChanged} />}
          {hasFeature("tags") && (
            <div className="relative">
              <button onClick={() => setTagMenu(!tagMenu)} className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2 py-0.5 text-[11px] text-slate-500 hover:border-slate-400">
                <TagIcon size={11} /> {t("Tag")}
              </button>
              {tagMenu && (
                <div className="absolute left-0 top-7 z-20 w-48 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                  {tags.length === 0 && <p className="p-2 text-xs text-slate-500">{t("Create tags in Settings.")}</p>}
                  {tags.map((tg) => (
                    <button key={tg.id} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-50"
                      onClick={() => { update({ tag_ids: tagIds.includes(tg.id) ? tagIds.filter((i) => i !== tg.id) : [...tagIds, tg.id] }); setTagMenu(false); }}>
                      <span className="h-3 w-3 rounded-full" style={{ background: tg.color }} /> <span className="flex-1">{tg.name}</span>
                      {tagIds.includes(tg.id) && <Check size={14} className="text-brand-600" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {hasFeature("ai_assist") && <span className="ml-auto" />}
          {hasFeature("ai_assist") && <SummaryCard conversation={conversation} onChanged={onChanged} />}
        </div>

        <div className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages === null && <div className="flex justify-center p-8 text-slate-400"><LoaderCircle className="animate-spin" /></div>}
          {messages?.map((m) => {
            if (m.is_note) {
              return (
                <div key={m.id} className="mx-auto max-w-[85%] rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm text-amber-950 sm:max-w-[70%]">
                  <p className="mb-0.5 flex items-center gap-1 text-[11px] font-semibold text-amber-800">{m.bot ? <Bot size={12} /> : <StickyNote size={12} />} {t("Internal note · {name}", { name: m.sender_name })}</p>
                  <p className="whitespace-pre-wrap break-words">{m.text}</p>
                  <p className="mt-1 text-[10px] text-amber-700">{t("{time} · only your team can see this", { time: clockTime(m.sent_at) })}</p>
                </div>
              );
            }
            const out = m.direction === "out";
            return (
              <div key={m.id} className={clsx("flex", out ? "justify-end" : "justify-start")}>
                <div className={clsx("max-w-[85%] sm:max-w-[70%]", out && "text-right")}>
                  <div className={clsx("inline-block whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-left text-sm shadow-sm",
                    out ? (m.bot ? "rounded-br-sm bg-violet-600 text-white" : "rounded-br-sm bg-brand-600 text-white") : "rounded-bl-sm border border-slate-200 bg-white text-slate-800",
                    m.status === "failed" && "bg-red-50 text-red-800 ring-1 ring-red-300")}>
                    <MessageFiles files={m.attachments} out={out} />
                    {m.text && !/^\[(image|video|audio|voice|document|sticker|photo|picture|file|attachment)\]$/.test(m.text) && (
                      <p className={m.attachments?.length ? "mt-1.5" : ""}>{m.text}</p>
                    )}
                    {!m.text && !m.attachments?.length && <span className="italic opacity-70">{t("(no text)")}</span>}
                  </div>
                  <p className={clsx("mt-1 flex items-center gap-1.5 px-1 text-[11px] text-slate-400", out && "justify-end")}>
                    {!out && <ProviderIcon provider={provider} size="xs" />}
                    {m.bot && <span className="inline-flex items-center gap-0.5 rounded bg-violet-100 px-1 font-medium text-violet-700"><Bot size={10} /> {m.bot === "ai" ? t("AI") : t("Auto")}</span>}
                    <span>{out && m.sender_name ? t("{name} · via {platform}", { name: m.sender_name, platform: ui.label }) : t("via {platform}", { platform: ui.label })} · {clockTime(m.sent_at)}</span>
                    {m.status === "pending" && <span>· {t("sending…")}</span>}
                    {m.status === "failed" && <span className="text-red-600" title={m.error}>· {t("failed")}</span>}
                  </p>
                  {m.status === "failed" && m.error && <p className="px-1 text-left text-[11px] text-red-600">{m.error.slice(0, 300)}</p>}
                  {m.bot && <SourcesLine sources={m.sources} className={clsx("mt-0.5 px-1", out && "justify-end")} />}
                </div>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>

        {hasFeature("orders") && <PaymentChecks conversationId={conversation.id} refreshKey={messages?.length ?? 0} onChanged={() => { load().catch(() => undefined); }} />}
        <form onSubmit={send} className={clsx("relative border-t p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:pb-3", mode === "note" ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-white")}
          onDragOver={(e) => { if (canAttach && e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragging(true); } }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { if (!canAttach) return; e.preventDefault(); setDragging(false); addFiles(Array.from(e.dataTransfer.files)); }}>
          {dragging && <div className="pointer-events-none absolute inset-1 z-10 flex items-center justify-center rounded-lg border-2 border-dashed border-brand-400 bg-brand-50/90 text-sm font-medium text-brand-700">{t("Drop files to attach")}</div>}
          {error && <p className="mb-2 rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-700">{error}</p>}
          {mode === "reply" && <PendingFiles files={files} onRemove={removeFile} />}
          <div className="mb-2 flex flex-wrap items-center gap-1 text-xs">
            <button type="button" onClick={() => setMode("reply")}
              className={clsx("inline-flex items-center gap-1 rounded-md px-2.5 py-1 font-medium", mode === "reply" ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100")}>
              <ProviderIcon provider={provider} size="xs" /> {isComment ? t("Reply publicly") : t("Reply via {platform}", { platform: ui.label })}
            </button>
            <button type="button" onClick={() => setMode("note")} title={hasFeature("internal_notes") ? "" : t("Pro plan")}
              className={clsx("inline-flex items-center gap-1 rounded-md px-2.5 py-1 font-medium", mode === "note" ? "bg-amber-500 text-white" : "text-slate-600 hover:bg-slate-100")}>
              <StickyNote size={13} /> {t("Internal note")}
            </button>
            {mode === "reply" && hasFeature("ai_assist") && (
              <>
                <span className="mx-1 h-4 w-px bg-slate-200" />
                <SuggestButton conversationId={conversation.id} onError={setError}
                  onDraft={(draft, missing, sources) => { setText(draft); setDraftSources(sources ?? []); setAiHint(missing ? t("Check before sending: {missing}", { missing }) : ""); }} />
                <RewriteMenu text={text} onText={setText} onError={setError} />
              </>
            )}
            {canned.length > 0 && mode === "reply" && <span className="ml-auto hidden text-slate-400 xl:inline">{t("Type / for saved replies")}</span>}
          </div>
          {draftSources.length > 0 && mode === "reply" && text && <SourcesLine sources={draftSources} className="mb-2" />}
          {aiHint && mode === "reply" && (
            <p className="mb-2 flex items-center gap-1 rounded-lg bg-violet-50 px-3 py-1.5 text-xs text-violet-800"><Bot size={12} /> {aiHint}</p>
          )}
          <div className="relative flex items-end gap-2">
            {suggestions.length > 0 && (
              <div className="absolute bottom-full left-0 z-20 mb-2 w-full max-w-md rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                {suggestions.map((c, i) => (
                  <button type="button" key={c.id} onMouseDown={(e) => { e.preventDefault(); setText(c.body); }}
                    className={clsx("block w-full rounded px-2.5 py-1.5 text-left", i === cannedIdx % suggestions.length ? "bg-brand-50" : "hover:bg-slate-50")}>
                    <span className="font-mono text-xs text-brand-700">/{c.shortcut}</span> <span className="text-sm font-medium">{c.title}</span>
                    <span className="block truncate text-xs text-slate-500">{c.body}</span>
                  </button>
                ))}
              </div>
            )}
            <textarea
              className={clsx("input max-h-40 min-h-[42px] resize-none", mode === "note" && "border-amber-300 bg-white")}
              rows={isEmail ? 3 : 1}
              placeholder={mode === "note" ? t("Write a note for your team (not sent to the customer)…")
                : touchKeyboard ? (isComment ? t("Reply publicly…") : t("Message…"))
                : isComment ? t("Reply publicly under their comment… (Enter to send)") : t("Reply via {platform}… (Enter to send)", { platform: ui.label })}
              value={text}
              onChange={(e) => { setText(e.target.value); setCannedIdx(0); }}
              onPaste={(e) => {
                const pasted = Array.from(e.clipboardData.files);
                if (pasted.length && canAttach && mode === "reply") { e.preventDefault(); addFiles(pasted); }
              }}
              onKeyDown={(e) => {
                if (suggestions.length > 0 && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
                  e.preventDefault();
                  setCannedIdx((i) => i + (e.key === "ArrowDown" ? 1 : suggestions.length - 1));
                  return;
                }
                if (suggestions.length > 0 && (e.key === "Enter" || e.key === "Tab")) {
                  e.preventDefault();
                  setText(suggestions[cannedIdx % suggestions.length].body);
                  return;
                }
                // phones: Enter adds a new line, the send button sends (like WhatsApp)
                if (e.key === "Enter" && !e.shiftKey && !touchKeyboard) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            {isComment && mode === "reply" && (
              <button type="button" className="btn-secondary h-[42px] whitespace-nowrap px-3 text-xs" disabled={sending || !text.trim()} title={t("Send this as a private message (DM) instead. Meta allows one per comment, within 7 days.")}
                onClick={async () => {
                  setSending(true); setError("");
                  try { await Api.privateReply(conversation.id, text.trim()); setText(""); } catch (err) { setError(err instanceof Error ? err.message : t("Failed")); }
                  finally { setSending(false); await load(); }
                }}>🔒 {t("Send privately")}</button>
            )}
            {canAttach && mode === "reply" && (
              <>
                <AttachButton onFiles={addFiles} disabled={sending || files.length >= 10} />
                {!text.trim() && !files.length && <VoiceRecorder disabled={sending} onRecorded={(blob, name) => upload(blob, name, "voice")} />}
              </>
            )}
            <button className={clsx("btn h-[42px] text-white", mode === "note" ? "bg-amber-500 hover:bg-amber-600" : "bg-brand-600 hover:bg-brand-700")}
              disabled={sending || uploading || (!text.trim() && !(mode === "reply" && readyFiles.length))} aria-label={mode === "note" ? t("Add note") : t("Send")}>
              {sending ? <LoaderCircle className="animate-spin" size={16} /> : mode === "note" ? <StickyNote size={16} /> : <Send size={16} />}
            </button>
          </div>
        </form>
      </div>

      {/* Contact panel */}
      <aside className="scroll-thin hidden w-72 shrink-0 flex-col overflow-y-auto border-l border-slate-200 bg-white xl:flex">
        <div className="flex flex-col items-center border-b border-slate-100 px-5 py-6 text-center">
          <div className="relative">
            <Avatar name={name} url={conversation.contact.avatar_url} size={64} />
            <ProviderIcon provider={provider} size="sm" className="absolute -bottom-1 -right-1 ring-2 ring-white" />
          </div>
          <p className="mt-3 font-semibold">{name}</p>
          {conversation.contact.handle && <p className="text-sm text-slate-500">{conversation.contact.handle}</p>}
        </div>
        <dl className="space-y-3 px-5 py-4 text-sm">
          <div><dt className="text-xs text-slate-500">{t("Channel")}</dt>
            <dd className="mt-1 flex items-center gap-2 font-medium"><ProviderIcon provider={provider} size="sm" /> {conversation.channel.name}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("Status")}</dt><dd className="mt-0.5 font-medium capitalize">{t(STATUS_LABELS[conversation.status] ?? conversation.status)}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("Assigned to")}</dt><dd className="mt-0.5 font-medium">{conversation.assigned_to?.name ?? t("Nobody")}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("Last message")}</dt><dd className="mt-0.5">{conversation.last_message_at ? new Date(conversation.last_message_at).toLocaleString() : "—"}</dd></div>
        </dl>
        {hasFeature("orders") && <CustomerPanel conversationId={conversation.id} />}
      </aside>
    </div>
  );
}
