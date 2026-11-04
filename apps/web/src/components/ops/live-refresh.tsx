"use client";

import { useEffect } from "react";

import { useRefresh } from "@/components/ops/use-refresh";

const MINUTE_MS = 60_000;

/**
 * Keeps a page of timers current for someone working from it (step 5.10): its server components
 * render again each minute while the tab is in view. What's being typed on the page stays.
 */
export function LiveRefresh() {
  const refresh = useRefresh();
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, MINUTE_MS);
    return () => {
      clearInterval(timer);
    };
  }, [refresh]);
  return null;
}
