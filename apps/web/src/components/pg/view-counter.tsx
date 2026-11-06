"use client";

import { useEffect } from "react";

import { browserApi } from "@/lib/api/browser";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Tells the API the PG's page was opened, for its owner's insights (step 7.6): once a session
 * per PG, so reloading doesn't count again. Nothing shows, and a failure is let go.
 */
export function ViewCounter({ slug }: { slug: string }) {
  useEffect(() => {
    const key = `viewed:${slug}`;
    try {
      if (sessionStorage.getItem(key) !== null) return;
      sessionStorage.setItem(key, "1");
    } catch {
      // No session storage: count it anyway.
    }
    void withCsrf((headers) =>
      browserApi.POST("/v1/listings/{slug}/views", { params: { path: { slug } }, headers }),
    ).catch(() => undefined);
  }, [slug]);
  return null;
}
