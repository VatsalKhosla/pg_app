"use client";

import { useReportWebVitals } from "next/web-vitals";
import { useEffect } from "react";

import { track } from "@/lib/analytics";
import { startBrowserAnalytics } from "@/lib/analytics-beacon";

/** What is reported of a metric. Next bundles web-vitals without its types, so they're here. */
interface WebVital {
  name: string;
  value: number;
  rating: string;
  navigationType: string;
}

// One reference for the page's whole life, so no metric is reported twice (Next's advice).
const reportWebVital = (metric: WebVital) => {
  track("web_vital", {
    name: metric.name,
    value: Math.round(metric.name === "CLS" ? metric.value * 1_000 : metric.value),
    rating: metric.rating,
    navigation: metric.navigationType,
    // The route, never its query, which may hold what someone searched for.
    path: window.location.pathname,
  });
};

/**
 * Turns on the browser's analytics when the server collects them (step 3.9, ADR 0035), and
 * reports each page's Core Web Vitals (CLS in thousandths, the rest in milliseconds).
 */
export function Analytics() {
  useEffect(() => startBrowserAnalytics(), []);
  useReportWebVitals(reportWebVital);
  return null;
}
