"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, LoaderCircle } from "lucide-react";
import { Api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { ShopSettings } from "@/lib/types";
import OrderEditor from "@/components/commerce/OrderEditor";

export default function NewOrderPage() {
  const t = useT();
  const [shop, setShop] = useState<ShopSettings | null>(null);
  const [conversationId, setConversationId] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    setConversationId(new URLSearchParams(window.location.search).get("conversation"));
    Api.shopSettings().then(setShop).catch(() => undefined);
  }, []);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <Link href={conversationId ? `/inbox?c=${conversationId}` : "/orders"} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
          <ArrowLeft size={16} /> {conversationId ? t("Back to the conversation") : t("Orders")}
        </Link>
        <h1 className="mb-5 mt-2 text-xl font-bold">{t("New order")}</h1>
        {shop && conversationId !== undefined ? <OrderEditor shop={shop} conversationId={conversationId} /> : <LoaderCircle className="animate-spin text-slate-400" />}
      </div>
    </div>
  );
}
