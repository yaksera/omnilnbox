"use client";

import { Api } from "./api";

const PREFS = "omni.notify";
type LocalPrefs = { sound: boolean; desktop: boolean };

export function localPrefs(): LocalPrefs {
  try {
    return { sound: true, desktop: true, ...JSON.parse(window.localStorage.getItem(PREFS) || "{}") };
  } catch {
    return { sound: true, desktop: true };
  }
}

export function saveLocalPrefs(p: LocalPrefs) {
  try { window.localStorage.setItem(PREFS, JSON.stringify(p)); } catch { /* storage blocked */ }
}

export const pushSupported = () =>
  typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export async function registerWorker() {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

function keyBytes(b64: string) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

/** Ask permission and subscribe this browser/phone to push notifications. */
export async function enablePush(): Promise<"on" | "denied" | "unsupported"> {
  if (!pushSupported()) return "unsupported";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  const reg = (await registerWorker()) ?? (await navigator.serviceWorker.ready);
  const { public_key } = await Api.pushKey();
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) });
  await Api.pushSubscribe(sub.toJSON());
  return "on";
}

export async function disablePush() {
  if (!pushSupported()) return;
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  if (sub) {
    await Api.pushUnsubscribe(sub.endpoint).catch(() => undefined);
    await sub.unsubscribe();
  }
}

export async function pushEnabledHere() {
  if (!pushSupported() || Notification.permission !== "granted") return false;
  const reg = await navigator.serviceWorker.getRegistration();
  return !!(await reg?.pushManager.getSubscription());
}

let audio: AudioContext | null = null;
/** Short two-tone chime (no sound file needed). */
export function chime() {
  try {
    audio = audio ?? new AudioContext();
    const t = audio.currentTime;
    [880, 1320].forEach((f, i) => {
      const o = audio!.createOscillator(), g = audio!.createGain();
      o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t + i * 0.12);
      g.gain.exponentialRampToValueAtTime(0.18, t + i * 0.12 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.12 + 0.25);
      o.connect(g).connect(audio!.destination);
      o.start(t + i * 0.12); o.stop(t + i * 0.12 + 0.3);
    });
  } catch { /* autoplay blocked until the user interacts */ }
}

/** In-page alert while OmniInbox is open (push covers when it's closed). */
export function desktopAlert(title: string, body: string) {
  if (typeof window === "undefined" || !("Notification" in window) || Notification.permission !== "granted") return;
  if (document.visibilityState === "visible") return;
  try {
    const n = new Notification(title, { body, icon: "/icons/icon-192.png", tag: "omni-inbox" });
    n.onclick = () => { window.focus(); n.close(); };
  } catch { /* some mobile browsers only allow notifications from the service worker */ }
}

// ---------------------------------------------------------------- installable app (PWA)
type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
let deferred: InstallEvent | null = null;
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e as InstallEvent; });
}
export const canPromptInstall = () => deferred !== null;
export const isInstalled = () => typeof window !== "undefined" && (window.matchMedia("(display-mode: standalone)").matches
  || (navigator as Navigator & { standalone?: boolean }).standalone === true);
export const isIOS = () => typeof navigator !== "undefined" && /iphone|ipad|ipod/i.test(navigator.userAgent);
export async function promptInstall() {
  if (!deferred) return false;
  await deferred.prompt();
  const { outcome } = await deferred.userChoice;
  deferred = null;
  return outcome === "accepted";
}
