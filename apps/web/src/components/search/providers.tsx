"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { type ReactNode, useState } from "react";

import { ApiError } from "@/lib/api/errors";

/** Once more after a failure, but not when the API said the request itself was wrong. */
function retry(failures: number, error: Error): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failures < 1;
}

/**
 * Search's client-side state (ADR 0031): the URL through nuqs, and the API's answers through
 * TanStack Query. Here rather than in the root layout, so other pages ship neither.
 */
export function SearchProviders({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry, refetchOnWindowFocus: false },
        },
      }),
  );
  return (
    <NuqsAdapter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </NuqsAdapter>
  );
}
