"use client";

import { useEffect } from "react";

/** Loads OmniInbox's own AI chat bubble on the marketing site, if one was set up with `manage.py setup_site_chat`. */
export default function SiteChat() {
  useEffect(() => {
    // Not on phones (it covers buttons on small screens) or inside the installed app
    const phone = window.matchMedia("(max-width: 767px)").matches;
    const installedApp = window.matchMedia("(display-mode: standalone)").matches;
    if (phone || installedApp || document.getElementById("omni-site-chat")) return;
    let cancelled = false;
    fetch("/backend/widget/site/")
      .then((r) => (r.ok ? r.json() : { channel: null }))
      .then(({ channel }: { channel: string | null }) => {
        if (cancelled || !channel || document.getElementById("omni-site-chat")) return;
        const s = document.createElement("script");
        s.id = "omni-site-chat";
        s.src = "/widget.js";
        s.async = true;
        s.dataset.channel = channel;
        document.body.appendChild(s);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);
  return null;
}
