"use client";

import { useRouter } from "next/navigation";
import { useCallback, useTransition } from "react";

/** Re-render the page's server components (the listing, its history) after a change. */
export function useRefresh(): () => void {
  const router = useRouter();
  const [, startTransition] = useTransition();
  return useCallback(() => {
    startTransition(() => {
      router.refresh();
    });
  }, [router]);
}
