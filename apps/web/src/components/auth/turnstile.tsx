"use client";

import { useEffect, useRef } from "react";

// Explicit rendering, so the widget appears only where it's needed and can be reset.
const SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

interface TurnstileApi {
  render(container: HTMLElement, options: Record<string, unknown>): string;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | undefined;

/** Cloudflare's script, once per page. It carries the page's nonce, which Turnstile passes on to
 * what it loads, so the Content Security Policy needs no 'unsafe-inline' (frame-src allows the
 * challenge, src/proxy.ts). */
function loadTurnstile(nonce: string | undefined): Promise<TurnstileApi> {
  if (window.turnstile !== undefined) return Promise.resolve(window.turnstile);
  loading ??= new Promise<TurnstileApi>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.async = true;
    if (nonce !== undefined) script.nonce = nonce;
    script.addEventListener("load", () => {
      if (window.turnstile === undefined) reject(new Error("Turnstile loaded without its API"));
      else resolve(window.turnstile);
    });
    script.addEventListener("error", () => {
      loading = undefined;
      reject(new Error("Turnstile couldn't load"));
    });
    document.head.append(script);
  });
  return loading;
}

/**
 * Cloudflare Turnstile's human check. `onToken` gets a token when the check passes, and null when
 * it expires or fails. A token works once: remount the widget (change its React `key`) for a new
 * one after it has been used.
 */
export function Turnstile({
  siteKey,
  action,
  nonce,
  onToken,
}: {
  siteKey: string;
  /** Which form this is; the API accepts only tokens solved for its own (otp_request). */
  action: string;
  nonce: string | undefined;
  onToken: (token: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const onTokenRef = useRef(onToken);
  useEffect(() => {
    onTokenRef.current = onToken;
  }, [onToken]);

  useEffect(() => {
    let widgetId: string | undefined;
    let cancelled = false;
    const report = (token: string | null) => {
      if (!cancelled) onTokenRef.current(token);
    };
    loadTurnstile(nonce)
      .then((turnstile) => {
        if (cancelled || container.current === null) return;
        widgetId = turnstile.render(container.current, {
          sitekey: siteKey,
          action,
          theme: "auto",
          callback: (token: string) => {
            report(token);
          },
          "expired-callback": () => {
            report(null);
          },
          "error-callback": () => {
            report(null);
          },
        });
      })
      .catch(() => {
        report(null);
      });
    return () => {
      cancelled = true;
      if (widgetId !== undefined) window.turnstile?.remove(widgetId);
    };
  }, [siteKey, action, nonce]);

  return <div ref={container} className="min-h-[65px]" />;
}
