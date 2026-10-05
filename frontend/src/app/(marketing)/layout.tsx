import Header from "@/components/marketing/Header";
import Footer from "@/components/marketing/Footer";
import SiteChat from "@/components/marketing/SiteChat";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <Header />
      <main className="flex-1">{children}</main>
      <Footer />
      <SiteChat />
    </div>
  );
}
