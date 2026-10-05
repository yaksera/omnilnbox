/* OmniInbox service worker: push notifications + installable app (PWA).
   API calls are never cached; pages fall back to the network. */
const VERSION = "omni-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "OmniInbox", body: event.data && event.data.text() }; }
  const title = data.title || "New message";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    tag: data.tag || undefined,
    renotify: !!data.tag,
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-96.png",
    data: { url: data.url || "/inbox" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data && event.notification.data.url || "/inbox", self.location.origin).href;
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of all) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.focus();
        client.postMessage({ type: "open", url });
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});

// Network-first for navigations with a tiny offline page; everything else goes straight to the network.
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.mode !== "navigate") return;
  event.respondWith(fetch(req).catch(() => new Response(
    '<!doctype html><meta name="viewport" content="width=device-width"><title>Offline</title>' +
    '<body style="font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0;color:#334155">' +
    '<div style="text-align:center"><h1 style="font-size:20px">You are offline</h1><p>OmniInbox will reconnect when your internet is back.</p>' +
    '<button onclick="location.reload()" style="padding:8px 16px;border-radius:8px;border:0;background:#4f46e5;color:#fff">Try again</button></div>',
    { headers: { "Content-Type": "text/html; charset=utf-8" } })));
});
self.VERSION = VERSION;
