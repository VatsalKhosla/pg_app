"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
// Often enough that the minutes shown are never more than a few seconds stale.
const TICK_MS = 15_000;

/**
 * How long a student who has moved in has left to tell us the room isn't as shown (step 5.6,
 * ADR 0050). It counts down to the booking's real `checkWindowEndsAt`, in whole minutes rounded
 * down, so it never shows more time than is left; it protects the student and asks them to buy
 * nothing (CLAUDE.md rule 7). The server's page shows the end itself; this adds what's left
 * once the browser knows its own time.
 */
export function CheckWindow({ endsAt }: { endsAt: string }) {
  const t = useTranslations("Bookings.window");
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => {
      setNow(Date.now());
    };
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, TICK_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, []);
  if (now === null) return null;
  const left = Date.parse(endsAt) - now;
  const hours = Math.floor(left / HOUR_MS);
  const minutes = Math.floor((left % HOUR_MS) / MINUTE_MS);
  const said =
    left <= 0
      ? t("over")
      : left < MINUTE_MS
        ? t("lastMinute")
        : hours > 0
          ? t("left", { hours, minutes })
          : t("leftMinutes", { minutes });
  return (
    <p role="timer" aria-live="off" className="font-medium">
      {said}
    </p>
  );
}
