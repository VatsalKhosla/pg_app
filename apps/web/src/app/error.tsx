"use client";

import { useEffect } from "react";

import { ErrorMessage } from "@/components/layout/error-message";
import { useErrorText } from "@/components/layout/error-text";
import { Button } from "@/components/ui/button";
import { captureError } from "@/lib/monitoring/capture-error";

// Shown, inside the site's layout, when rendering a page fails. `retry` fetches and renders the
// page again. The digest identifies the error in the server logs without exposing its details.
export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  const text = useErrorText();

  useEffect(() => {
    captureError(error);
  }, [error]);

  return (
    <ErrorMessage
      title={text.title}
      body={text.body}
      detail={error.digest === undefined ? undefined : `${text.referenceLabel}: ${error.digest}`}
      action={<Button onClick={retry}>{text.retry}</Button>}
    />
  );
}
