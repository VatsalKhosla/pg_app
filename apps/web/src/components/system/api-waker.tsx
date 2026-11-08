"use client";

import { useEffect, useState } from "react";

import { browserApi } from "@/lib/api/browser";

/** How often to look, and for how long, while the API starts: about a minute, usually. */
const POLL_MS = 4_000;
const GIVE_UP_MS = 180_000;

async function isAwake(): Promise<boolean> {
  try {
    const { response } = await browserApi.GET("/v1/policies");
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * The test site's API sleeps after 15 idle minutes (its host's free plan), and the host doesn't
 * wake it for the web app's own requests, only for a visitor's. So when the API is asleep, this
 * asks it to wake from the visitor's browser, says so, and reloads the page once it answers.
 */
export function ApiWaker({
  wakeUrl,
  text,
  pollMs = POLL_MS,
  onAwake = () => {
    window.location.reload();
  },
}: {
  wakeUrl: string;
  text: string;
  pollMs?: number;
  onAwake?: () => void;
}) {
  const [waking, setWaking] = useState(false);

  useEffect(() => {
    let stop = false;
    let busy = false;
    const stopped = () => stop;
    let timer: number | undefined;

    async function wake() {
      setWaking(true);
      // The reply can't be read across origins, and needn't be: the request is what counts.
      void fetch(`${wakeUrl}/healthz`, { mode: "no-cors", cache: "no-store" }).catch(
        () => undefined,
      );
      const deadline = Date.now() + GIVE_UP_MS;
      while (!stopped() && Date.now() < deadline) {
        await new Promise((resolve) => {
          timer = window.setTimeout(resolve, pollMs);
        });
        if (stopped()) return;
        if (await isAwake()) {
          if (!stopped()) onAwake();
          break;
        }
      }
      if (!stopped()) setWaking(false);
    }

    async function check() {
      if (busy || stopped()) return;
      busy = true;
      if (!(await isAwake()) && !stopped()) await wake();
      busy = false;
    }

    // Also on coming back to the tab: the API may have gone to sleep in the meantime.
    function onVisible() {
      if (document.visibilityState === "visible") void check();
    }

    void check();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stop = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [wakeUrl, pollMs, onAwake]);

  if (!waking) return null;
  return (
    <p
      role="status"
      className="glass fixed inset-x-3 bottom-3 z-50 mx-auto max-w-xl rounded-2xl px-4 py-3 text-center text-sm font-medium text-foreground shadow-lg"
    >
      {text}
    </p>
  );
}
