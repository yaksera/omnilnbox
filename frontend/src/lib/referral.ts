"use client";

/**
 * Affiliate attribution in the browser.
 *
 * A visit to /r/CODE or any page with ?ref=CODE remembers the code for REMEMBER_DAYS.
 * The sign-up form then sends it with the new account, so the affiliate gets credit
 * (and recurring commission) even if the visitor signs up days later.
 */
import { Api } from "./api";

const KEY = "omni.ref";
const REMEMBER_DAYS = 60;

export type StoredReferral = { code: string; at: number };

export function normalizeCode(code: string) {
  return code.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 20);
}

export function getStoredReferral(): StoredReferral | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const ref = JSON.parse(raw) as StoredReferral;
    if (!ref.code || Date.now() - ref.at > REMEMBER_DAYS * 86400000) {
      window.localStorage.removeItem(KEY);
      return null;
    }
    return ref;
  } catch {
    return null;
  }
}

export function clearStoredReferral() {
  try { window.localStorage.removeItem(KEY); } catch { /* storage blocked */ }
}

const inflight = new Map<string, Promise<boolean>>();  // one click per code per page load (React may run effects twice)

/** Record the click and remember the code (only if it belongs to an approved affiliate). */
export function captureReferral(rawCode: string, landing = "") {
  const code = normalizeCode(rawCode);
  if (code.length < 4) return Promise.resolve(false);
  if (!inflight.has(code)) inflight.set(code, record(code, landing));
  return inflight.get(code)!;
}

async function record(code: string, landing: string) {
  try {
    const res = await Api.affiliateClick({ code, landing: landing || window.location.pathname, referrer: document.referrer.slice(0, 300) });
    if (!res.valid) return false;
    window.localStorage.setItem(KEY, JSON.stringify({ code: res.code, at: Date.now() } satisfies StoredReferral));
    return true;
  } catch {
    return false;
  }
}
