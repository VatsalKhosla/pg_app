"use client";

import dynamic from "next/dynamic";
import { type ComponentProps, useEffect, useRef, useState } from "react";

import type { QuoteChecker as Checker } from "./quote-checker";

const placeholder = () => (
  <div className="min-h-80 w-full animate-pulse rounded-xl bg-muted motion-reduce:animate-none" />
);

const QuoteChecker = dynamic(
  () => import("./quote-checker").then((module) => module.QuoteChecker),
  {
    ssr: false,
    loading: placeholder,
  },
);

/**
 * The price check (step 4.5), whose code (its form, validation and API calls) loads once it
 * scrolls near the screen, as the map's does: on a phone it sits below the first screen, so a PG's
 * page doesn't pay for it until someone scrolls to it (ADR 0066).
 */
export function QuoteCheckerNear(props: ComponentProps<typeof Checker>) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (element === null) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);

  return <div ref={ref}>{near ? <QuoteChecker {...props} /> : placeholder()}</div>;
}
