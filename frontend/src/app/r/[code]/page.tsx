"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle } from "lucide-react";
import { captureReferral } from "@/lib/referral";

/** Affiliate tracking link: /r/CODE -> remember the code, then show the home page. */
export default function ReferralRedirect({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const router = useRouter();
  useEffect(() => {
    captureReferral(code, `/r/${code}`).finally(() => router.replace("/"));
  }, [code, router]);
  return <div className="flex min-h-screen items-center justify-center text-slate-400"><LoaderCircle className="animate-spin" /></div>;
}
