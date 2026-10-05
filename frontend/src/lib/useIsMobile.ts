"use client";

import { useEffect, useState } from "react";

const QUERY = "(max-width: 767px)";  // Tailwind's md breakpoint

/** True on phone-sized screens. Updates when the window is resized or the phone is rotated. */
export function useIsMobile() {
  const [mobile, setMobile] = useState(() => typeof window !== "undefined" && window.matchMedia(QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(QUERY);
    const on = () => setMobile(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return mobile;
}
