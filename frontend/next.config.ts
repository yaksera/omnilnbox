import type { NextConfig } from "next";

// Where the Django API runs. The browser never calls it directly: Next.js proxies
// /backend/* -> BACKEND_URL/api/*, so there are no CORS or port mismatches.
// Use 127.0.0.1 (not "localhost") because Node on Windows resolves localhost to IPv6 ::1,
// while `manage.py runserver` only listens on IPv4.
const BACKEND_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const isDev = process.env.NODE_ENV !== "production";
// Django admin path: keep it secret in production (same value as ADMIN_URL in backend/.env, e.g. "staff-8f3k2/")
const ADMIN = (process.env.DJANGO_ADMIN_PATH || "admin").replace(/^\/+|\/+$/g, "");
const directApi = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

// Content-Security-Policy: blocks injected scripts from other origins, framing (clickjacking),
// and form posts/data exfiltration to foreign hosts. Next.js needs inline scripts for hydration;
// dev mode additionally needs eval + websocket for hot reload.
const csp = [
  "default-src 'self'",
  // connect.facebook.net: the Facebook SDK for one-click "Connect with Facebook" (Channels page)
  `script-src 'self' 'unsafe-inline' https://connect.facebook.net${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:", // contact avatars come from platform CDNs
  "font-src 'self' data:",
  "media-src 'self' blob:", // voice notes and videos in conversations
  "frame-src 'self' https://www.facebook.com https://web.facebook.com https://staticxx.facebook.com",
  `connect-src 'self' https://graph.facebook.com https://www.facebook.com${directApi ? ` ${directApi}` : ""}${isDev ? " ws: wss:" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  // eSewa checkout is a browser form POST to eSewa (billing + shop payment links)
  "form-action 'self' https://rc-epay.esewa.com.np https://epay.esewa.com.np",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=(), payment=()" },
  ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]),
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Dev only: let `npm run dev` serve its scripts/hot reload when the app is opened through a tunnel
  // (ngrok, Cloudflare) instead of localhost. Without this the page loads but stays blank / buttons do nothing.
  allowedDevOrigins: ["*.ngrok-free.dev", "*.ngrok-free.app", "*.ngrok.app", "*.trycloudflare.com"],
  // The /backend proxy buffers request bodies (10MB by default); publishing uploads videos up to 500MB.
  experimental: { proxyClientMaxBodySize: "520mb" },
  async headers() {
    return [
      // Everything except the website chat widget: no framing (clickjacking protection)
      { source: "/:path((?!widget/).*)", headers: securityHeaders },
      // The chat widget runs inside an iframe on the shop's own website
      {
        source: "/widget/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp.replace("frame-ancestors 'none'", "frame-ancestors *") },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
  // Django URLs end with "/" — don't let Next strip it (POST to a slash-less URL fails in Django).
  skipTrailingSlashRedirect: true,
 async rewrites() {
  return [
    { source: "/backend/:path*/", destination: `${BACKEND_URL}/api/:path*/` },
    { source: "/backend/:path*", destination: `${BACKEND_URL}/api/:path*` },
    // public URLs Meta/Google/TikTok call: media files, webhooks, OAuth callbacks
    { source: "/api/:path*/", destination: `${BACKEND_URL}/api/:path*/` },
    { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
    // Django admin (/admin/) and its CSS/JS, so it also opens through ngrok. Our own /admin-panel page is not affected.
    { source: `/${ADMIN}`, destination: `${BACKEND_URL}/${ADMIN}/` },
    { source: `/${ADMIN}/:path*/`, destination: `${BACKEND_URL}/${ADMIN}/:path*/` },
    { source: `/${ADMIN}/:path*`, destination: `${BACKEND_URL}/${ADMIN}/:path*` },
    { source: "/static/:path*", destination: `${BACKEND_URL}/static/:path*` },
  ];
},
};

export default nextConfig;
