/* OmniInbox website chat. Paste on your site:
   <script src="https://YOUR-OMNIINBOX-DOMAIN/widget.js" data-channel="CHANNEL-ID" async></script> */
(function () {
  var s = document.currentScript || document.querySelector('script[data-channel][src*="widget.js"]');
  if (!s || window.__omniWidget) return;
  window.__omniWidget = true;
  var channel = s.getAttribute("data-channel");
  var origin = new URL(s.src).origin;
  var side = s.getAttribute("data-position") === "left" ? "left" : "right";
  var color = s.getAttribute("data-color") || "#4f46e5";
  var open = false;

  var btn = document.createElement("button");
  btn.type = "button";
  btn.setAttribute("aria-label", "Chat with us");
  btn.style.cssText = "position:fixed;bottom:20px;" + side + ":20px;width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;" +
    "box-shadow:0 8px 24px rgba(0,0,0,.2);z-index:2147483646;display:flex;align-items:center;justify-content:center;background:" + color;
  var chat = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  var close = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  btn.innerHTML = chat;

  var badge = document.createElement("span");
  badge.style.cssText = "position:absolute;top:2px;right:2px;width:14px;height:14px;border-radius:50%;background:#ef4444;border:2px solid #fff;display:none";
  btn.appendChild(badge);

  var frame = document.createElement("iframe");
  frame.title = "Chat";
  frame.src = origin + "/widget/" + encodeURIComponent(channel) + "?embed=1";
  frame.style.cssText = "position:fixed;bottom:90px;" + side + ":20px;width:370px;height:560px;max-width:calc(100vw - 24px);max-height:calc(100vh - 110px);" +
    "border:0;border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,.25);z-index:2147483647;display:none;background:#fff";

  function toggle() {
    open = !open;
    frame.style.display = open ? "block" : "none";
    btn.innerHTML = open ? close : chat;
    btn.appendChild(badge);
    badge.style.display = "none";
    frame.contentWindow && frame.contentWindow.postMessage({ type: "omni:open", open: open }, origin);
  }
  btn.addEventListener("click", toggle);

  window.addEventListener("message", function (e) {
    if (e.origin !== origin || !e.data) return;
    if (e.data.type === "omni:config" && e.data.color && /^#[0-9a-fA-F]{6}$/.test(e.data.color) && !s.getAttribute("data-color")) btn.style.background = e.data.color;
    if (e.data.type === "omni:unread" && !open) badge.style.display = "block";
    if (e.data.type === "omni:close" && open) toggle();
  });

  function mount() { document.body.appendChild(frame); document.body.appendChild(btn); }
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
