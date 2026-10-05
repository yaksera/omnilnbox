"use client";

import { useEffect, useRef } from "react";
import { Api, auth } from "@/lib/api";

/**
 * Instant updates: one long-poll loop per browser tab (GET /events/ waits until something changes in the
 * workspace), shared by every component that subscribes. Components reload their data when notified.
 */
type Listener = () => void;
const listeners = new Set<Listener>();
let running = false;
let controller: AbortController | null = null;

async function loop() {
  running = true;
  let v = "";
  let failures = 0;
  while (listeners.size > 0 && auth.access) {
    controller = new AbortController();
    try {
      const res = await Api.events(v, controller.signal);
      failures = 0;
      if (res.changed) listeners.forEach((fn) => { try { fn(); } catch { /* a listener failed */ } });
      v = res.v;
    } catch {
      if (!listeners.size) break;
      failures += 1;
      await new Promise((r) => setTimeout(r, Math.min(30000, 1500 * failures)));  // server restarting / offline
    }
  }
  running = false;
  controller = null;
}

export function subscribe(fn: Listener) {
  listeners.add(fn);
  if (!running) void loop();
  return () => {
    listeners.delete(fn);
    if (!listeners.size) controller?.abort();
  };
}

/** Call `onChange` whenever something changes in the current workspace (new message, assignment, file ready...). */
export function useLiveUpdates(onChange: () => void) {
  const ref = useRef(onChange);
  useEffect(() => { ref.current = onChange; }, [onChange]);
  useEffect(() => subscribe(() => ref.current()), []);
}
