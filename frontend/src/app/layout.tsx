import type { Metadata, Viewport } from "next";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n";
import ReferralCapture from "@/components/affiliate/ReferralCapture";

export const metadata: Metadata = {
  title: "OmniInbox — every customer message in one place",
  description: "Unified inbox for WhatsApp, Instagram, Messenger, TikTok, Viber, Telegram, Discord, Gmail, Outlook, Zoho Mail and your website.",
  appleWebApp: { capable: true, title: "OmniInbox", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
  // iPhone browsers turn numbers, dates and addresses into links before React loads, which breaks hydration
  // (and phone numbers in chats / prices like "Rs 4,80,000" shouldn't become tap-to-call links anyway).
  formatDetection: { telephone: false, date: false, address: false, email: false },
};

// viewportFit "cover" + env(safe-area-inset-*) keeps the app clear of the notch and home bar on phones
export const viewport: Viewport = { themeColor: "#4f46e5", viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: browsers (translation, extensions) may add attributes to <html>/<body> before React loads
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full bg-slate-50 text-slate-900" suppressHydrationWarning><I18nProvider><ReferralCapture />{children}</I18nProvider></body>
    </html>
  );
}
