import { type AnalyticsEvent, type AnalyticsProperties, setAnalyticsTransport } from "./analytics";

/**
 * Analytics from the browser (step 3.9, ADR 0035), sent to the site's own /api/events, which
 * passes them on to PostHog without the visitor's address. Events wait in a short queue and go
 * together, a few seconds later or when the page is hidden, whichever comes first (sendBeacon
 * still delivers as the page closes).
 *
 * Each tab gets an anonymous id, kept in sessionStorage: it ends with the tab and is never tied
 * to an account. A visit request carries it, so the visit's later steps join the same funnel. A
 * browser that asks not to be tracked (Global Privacy Control, Do Not Track) gets no id and
 * sends nothing.
 */

export const EVENTS_PATH = "/api/events";
const STORAGE_KEY = "analytics-id";
const FLUSH_AFTER_MS = 5_000;
// The most /api/events takes in one request.
export const MAX_BATCH = 20;

export interface QueuedEvent {
  uuid: string;
  event: AnalyticsEvent;
  timestamp: string;
  properties: AnalyticsProperties;
}

export interface EventsBody {
  distinctId: string;
  sentAt: string;
  events: QueuedEvent[];
}

type PrivacyNavigator = Pick<Navigator, "doNotTrack"> & { globalPrivacyControl?: boolean };

/** Whether the browser lets the site report analytics. */
export function trackingAllowed(browser: PrivacyNavigator = navigator): boolean {
  return browser.globalPrivacyControl !== true && browser.doNotTrack !== "1";
}

let started = false;

/** The tab's anonymous id once analytics have started, else undefined. */
export function analyticsId(): string | undefined {
  if (!started) return undefined;
  try {
    const kept = sessionStorage.getItem(STORAGE_KEY);
    if (kept !== null) return kept;
    const made = crypto.randomUUID();
    sessionStorage.setItem(STORAGE_KEY, made);
    return made;
  } catch {
    // Storage blocked, or no crypto.randomUUID (an insecure page): no id, so nothing is sent.
    return undefined;
  }
}

/** Send `body`, by beacon if the page may be closing, else by a fetch that outlives it. */
function send(body: EventsBody, closing: boolean): void {
  const json = JSON.stringify(body);
  if (
    closing &&
    navigator.sendBeacon(EVENTS_PATH, new Blob([json], { type: "application/json" }))
  ) {
    return;
  }
  void fetch(EVENTS_PATH, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: json,
    keepalive: true,
  }).catch(() => {
    // Analytics never get in the way: a lost batch is only lost.
  });
}

/** Start reporting this tab's analytics; the returned function stops it. */
export function startBrowserAnalytics(): () => void {
  if (!trackingAllowed()) {
    setAnalyticsTransport(null);
    return () => undefined;
  }
  started = true;
  const queue: QueuedEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;

  function flush(closing: boolean) {
    clearTimeout(timer);
    timer = undefined;
    const distinctId = analyticsId();
    while (queue.length > 0) {
      const events = queue.splice(0, MAX_BATCH);
      if (distinctId !== undefined) {
        send({ distinctId, sentAt: new Date().toISOString(), events }, closing);
      }
    }
  }

  function onHidden() {
    if (document.visibilityState === "hidden") flush(true);
  }

  // Leaving the page, which may still say it's visible as it goes.
  function onLeave() {
    flush(true);
  }

  setAnalyticsTransport({
    capture(event, properties) {
      queue.push({
        uuid: crypto.randomUUID(),
        event,
        timestamp: new Date().toISOString(),
        properties,
      });
      if (queue.length >= MAX_BATCH) flush(false);
      else
        timer ??= setTimeout(() => {
          flush(false);
        }, FLUSH_AFTER_MS);
    },
  });
  document.addEventListener("visibilitychange", onHidden);
  window.addEventListener("pagehide", onLeave);
  return () => {
    flush(false);
    document.removeEventListener("visibilitychange", onHidden);
    window.removeEventListener("pagehide", onLeave);
    setAnalyticsTransport(null);
    started = false;
  };
}
