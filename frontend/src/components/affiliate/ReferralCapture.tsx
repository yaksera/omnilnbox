"use client";

import { useEffect } from "react";
import { captureReferral } from "@/lib/referral";

/** Picks up ?ref=CODE on any page (e.g. omniinbox.com/pricing?ref=RAM2026) and remembers it for sign-up. */
export default function ReferralCapture() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("ref");
    if (!code) return;
    captureReferral(code).finally(() => {
      params.delete("ref");
      const q = params.toString();
      window.history.replaceState(null, "", `${window.location.pathname}${q ? `?${q}` : ""}${window.location.hash}`);
    });
  }, []);
  return null;
}
