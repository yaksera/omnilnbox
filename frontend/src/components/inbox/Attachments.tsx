"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Download, FileText, LoaderCircle, Mic, Paperclip, Receipt, Sparkles, Square, Trash2, TriangleAlert, X } from "lucide-react";
import type { Attachment } from "@/lib/types";
import { useT } from "@/lib/i18n";

export const MAX_FILE_MB = 25;

export function formatSize(bytes: number) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Photos, videos, voice notes and files inside a message bubble. */
export function MessageFiles({ files, out }: { files: Attachment[]; out: boolean }) {
  const t = useT();
  const [zoom, setZoom] = useState<Attachment | null>(null);
  if (!files?.length) return null;
  return (
    <div className="mt-1 space-y-1.5 first:mt-0">
      {files.map((f, i) => {
        const key = f.id || `${f.name}-${i}`;
        if (f.status === "pending") {
          return <p key={key} className="flex items-center gap-1.5 text-xs opacity-80"><LoaderCircle size={13} className="animate-spin" /> {t("Downloading {name}…", { name: f.kind === "file" ? f.name || t("file") : t(f.kind) })}</p>;
        }
        if (f.status !== "ready" || !f.url) {
          return (
            <p key={key} className="flex items-center gap-1.5 text-xs opacity-80" title={f.error}>
              <TriangleAlert size={13} /> {f.status === "failed" ? t("Couldn't download this file") : t("{name} (not available)", { name: t(labelFor(f)) })}
            </p>
          );
        }
        if (f.kind === "image" || f.kind === "sticker") {
          return (
            <div key={key}>
              <button type="button" onClick={() => setZoom(f)} className="block overflow-hidden rounded-xl">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={f.url} alt={f.ai?.description || f.name || t("Photo")} loading="lazy"
                  className={clsx("max-h-72 w-auto max-w-full object-cover", f.kind === "sticker" && "max-h-32 bg-transparent")} />
              </button>
              {f.ai?.is_payment && <p className="mt-1 flex items-center gap-1 text-[11px] opacity-80"><Receipt size={12} /> {t("Payment screenshot: checked by AI, see Payments")}</p>}
            </div>
          );
        }
        if (f.kind === "video") {
          return <video key={key} src={f.url} controls preload="metadata" className="max-h-72 max-w-full rounded-xl bg-black" />;
        }
        if (f.kind === "audio" || f.kind === "voice") {
          return (
            <div key={key} className="max-w-xs">
              <div className="flex items-center gap-2">
                {f.kind === "voice" && <Mic size={14} className="shrink-0 opacity-80" />}
                <audio src={f.url} controls preload="metadata" className="h-9 w-60 max-w-full" />
              </div>
              {f.transcript && (
                <p className={clsx("mt-1.5 rounded-lg px-2.5 py-1.5 text-sm", out ? "bg-white/15" : "bg-slate-100")}>
                  <span className="mb-0.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide opacity-70"><Sparkles size={11} /> {t("Transcript")}</span>
                  {f.transcript}
                </p>
              )}
            </div>
          );
        }
        return (
          <a key={key} href={`${f.url}?download=1`} className={clsx("flex items-center gap-2.5 rounded-xl px-3 py-2 text-left no-underline",
            out ? "bg-white/15 hover:bg-white/25" : "bg-slate-100 hover:bg-slate-200")}>
            <FileText size={22} className="shrink-0" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{f.name || t("File")}</span>
              <span className="block text-[11px] opacity-75">{formatSize(f.size)}{f.mime === "application/pdf" && " · PDF"}</span>
            </span>
            <Download size={16} className="shrink-0 opacity-80" />
          </a>
        );
      })}
      {zoom && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4" onClick={() => setZoom(null)} role="dialog" aria-label={t("Photo")}>
          <button type="button" className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20" aria-label={t("Close")}><X size={20} /></button>
          <a href={`${zoom.url}?download=1`} onClick={(e) => e.stopPropagation()} className="absolute bottom-4 right-4 inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-2 text-sm text-white hover:bg-white/20"><Download size={16} /> {t("Download")}</a>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={zoom.url} alt={zoom.name} className="max-h-full max-w-full rounded-lg object-contain" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

function labelFor(f: Attachment) {
  return { image: "Photo", video: "Video", audio: "Audio", voice: "Voice message", sticker: "Sticker", file: f.name || "File" }[f.kind] ?? "File";
}

/** A file being attached in the composer. */
export type PendingFile = { key: string; name: string; kind: string; progress: number; preview?: string; att?: Attachment; error?: string };

export function PendingFiles({ files, onRemove }: { files: PendingFile[]; onRemove: (key: string) => void }) {
  const t = useT();
  if (!files.length) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {files.map((f) => (
        <div key={f.key} className={clsx("relative flex max-w-[220px] items-center gap-2 rounded-lg border bg-white py-1.5 pl-1.5 pr-7 text-xs",
          f.error ? "border-red-300 text-red-700" : "border-slate-200 text-slate-700")}>
          {f.preview
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={f.preview} alt="" className="h-9 w-9 rounded object-cover" />
            : <span className="flex h-9 w-9 items-center justify-center rounded bg-slate-100">{f.kind === "voice" ? <Mic size={16} /> : <FileText size={16} />}</span>}
          <span className="min-w-0">
            <span className="block truncate font-medium">{f.name}</span>
            <span className="block text-[11px] text-slate-500">
              {f.error ? f.error : f.att ? formatSize(f.att.size) : t("Uploading… {n}%", { n: f.progress })}
            </span>
          </span>
          {!f.att && !f.error && <LoaderCircle size={14} className="absolute right-2 top-2 animate-spin text-slate-400" />}
          {(f.att || f.error) && (
            <button type="button" onClick={() => onRemove(f.key)} aria-label={t("Remove {name}", { name: f.name })} className="absolute right-1.5 top-1.5 rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X size={13} /></button>
          )}
        </div>
      ))}
    </div>
  );
}

export function AttachButton({ onFiles, disabled }: { onFiles: (files: File[]) => void; disabled?: boolean }) {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className="btn-ghost h-[42px] px-2.5 text-slate-500" disabled={disabled} onClick={() => input.current?.click()}
        title={t("Attach photos, videos or files (max {n} MB each)", { n: MAX_FILE_MB })} aria-label={t("Attach files")}>
        <Paperclip size={18} />
      </button>
      <input ref={input} type="file" multiple hidden onChange={(e) => { onFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
    </>
  );
}

function pickMime() {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/mp4", "audio/webm"]) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

/** Record a voice note with the microphone. Converted to a WhatsApp/Telegram-friendly voice message on the server. */
export function VoiceRecorder({ onRecorded, disabled }: { onRecorded: (blob: Blob, name: string) => void; disabled?: boolean }) {
  const t = useT();
  const [state, setState] = useState<"idle" | "recording">("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const keep = useRef(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); rec.current?.stream.getTracks().forEach((tr) => tr.stop()); }, []);

  async function start() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMime();
      const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      keep.current = true;
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        if (timer.current) clearInterval(timer.current);
        setState("idle");
        if (!keep.current || !chunks.current.length) return;
        const type = r.mimeType || mime || "audio/webm";
        const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
        onRecorded(new Blob(chunks.current, { type }), `voice-note.${ext}`);
      };
      r.start(250);
      rec.current = r;
      setSeconds(0);
      setState("recording");
      timer.current = setInterval(() => setSeconds((s) => {
        if (s + 1 >= 300 && r.state === "recording") r.stop();  // 5-minute limit
        return s + 1;
      }), 1000);
    } catch {
      setError(t("Allow microphone access in your browser to record a voice note."));
    }
  }

  function stop(save: boolean) {
    keep.current = save;
    if (rec.current?.state === "recording") rec.current.stop();
  }

  if (state === "recording") {
    return (
      <div className="flex h-[42px] items-center gap-1 rounded-lg bg-red-50 pl-2.5 pr-1 text-sm text-red-700">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-600" />
        <span className="w-10 tabular-nums">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span>
        <button type="button" onClick={() => stop(false)} className="rounded p-1.5 hover:bg-red-100" aria-label={t("Discard recording")} title={t("Discard")}><Trash2 size={16} /></button>
        <button type="button" onClick={() => stop(true)} className="rounded bg-red-600 p-1.5 text-white hover:bg-red-700" aria-label={t("Stop and attach")} title={t("Stop and attach")}><Square size={14} /></button>
      </div>
    );
  }
  return (
    <>
      <button type="button" className="btn-ghost h-[42px] px-2.5 text-slate-500" disabled={disabled || typeof window === "undefined"} onClick={start}
        title={error || t("Record a voice note")} aria-label={t("Record a voice note")}>
        <Mic size={18} className={error ? "text-red-500" : ""} />
      </button>
    </>
  );
}
