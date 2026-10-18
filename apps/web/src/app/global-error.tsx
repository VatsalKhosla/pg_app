"use client";

import "./globals.css";

import { useEffect } from "react";

import { ErrorMessage } from "@/components/layout/error-message";
import { Button } from "@/components/ui/button";
import { brandStyle } from "@/config/brand";
import { defaultLocale } from "@/i18n/config";
import { captureError } from "@/lib/monitoring/capture-error";

import messages from "../../messages/en-IN.json";

// Replaces the root layout when that layout itself fails, so it brings its own <html> and <body>
// and can't rely on anything the layout provides; it reads the message file directly instead.
export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  const text = messages.Error;

  useEffect(() => {
    captureError(error);
  }, [error]);

  return (
    <html lang={defaultLocale} style={brandStyle}>
      <body className="flex min-h-dvh flex-col font-sans antialiased">
        <title>{text.title}</title>
        <main className="flex flex-1 flex-col">
          <ErrorMessage
            title={text.title}
            body={text.body}
            detail={
              error.digest === undefined ? undefined : `${text.referenceLabel}: ${error.digest}`
            }
            action={<Button onClick={retry}>{text.retry}</Button>}
          />
        </main>
      </body>
    </html>
  );
}
