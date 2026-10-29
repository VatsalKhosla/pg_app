"use client";

import { useEffect } from "react";

import { type AnalyticsEvent, type AnalyticsProperties, track } from "@/lib/analytics";

/** Reports `event` once, when the page it's on is shown (step 3.9). */
export function TrackView({
  event,
  properties,
}: {
  event: AnalyticsEvent;
  properties: AnalyticsProperties;
}) {
  // The properties are fixed for the page, so their text is a stable dependency.
  const key = JSON.stringify(properties);
  useEffect(() => {
    track(event, JSON.parse(key) as AnalyticsProperties);
  }, [event, key]);
  return null;
}
