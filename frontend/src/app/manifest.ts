import type { MetadataRoute } from "next";

// Installable app (PWA): "Add to Home Screen" on phones, "Install" in Chrome/Edge on computers.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "OmniInbox",
    short_name: "OmniInbox",
    description: "Every customer message, order and post in one place.",
    start_url: "/inbox",
    scope: "/",
    display: "standalone",
    background_color: "#f8fafc",
    theme_color: "#4f46e5",
    orientation: "portrait-primary",
    categories: ["business", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Inbox", url: "/inbox" },
      { name: "Orders", url: "/orders" },
      { name: "New order", url: "/orders/new" },
    ],
  };
}
