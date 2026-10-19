"use client";

import { useState } from "react";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { askForData, type DataRequest } from "@/lib/auth/client";

export interface DataRequestsText {
  exportButton: string;
  deletionButton: string;
  deletionConfirm: string;
  status: {
    exportReceived: string;
    exportReady: string;
    exportExpired: string;
    deletionReceived: string;
    deletionCompleted: string;
    deletionRejected: string;
  };
  download: string;
  errors: Record<string, string>;
}

/**
 * The person's own data requests (DPDP): a copy of their data, which is ready within minutes and
 * kept for a week, and their account's deletion, which the team handles.
 */
export function DataRequests({
  text,
  initial,
  apiOrigin,
  formatDate,
}: {
  text: DataRequestsText;
  initial: readonly DataRequest[];
  apiOrigin: string;
  /** Dates as the page's locale writes them, keyed by the ISO strings that may appear. */
  formatDate: Record<string, string>;
}) {
  const [requests, setRequests] = useState<readonly DataRequest[]>(initial);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function ask(kind: "export" | "deletion") {
    if (kind === "deletion" && !window.confirm(text.deletionConfirm)) return;
    setBusy(true);
    setFailure(null);
    askForData(kind).then(
      (request) => {
        setRequests((current) => [request, ...current.filter((item) => item.id !== request.id)]);
        setBusy(false);
      },
      (error: unknown) => {
        setFailure(problemMessage(error, text.errors));
        setBusy(false);
      },
    );
  }

  function describe(request: DataRequest): string {
    const until = request.expiresAt === null ? "" : (formatDate[request.expiresAt] ?? "");
    if (request.kind === "export") {
      if (request.status === "ready") return text.status.exportReady.replace("{date}", until);
      if (request.status === "expired") return text.status.exportExpired;
      return text.status.exportReceived;
    }
    if (request.status === "completed") return text.status.deletionCompleted;
    if (request.status === "rejected") {
      return text.status.deletionRejected.replace("{note}", request.note ?? "");
    }
    return text.status.deletionReceived;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => {
            ask("export");
          }}
        >
          {text.exportButton}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => {
            ask("deletion");
          }}
        >
          {text.deletionButton}
        </Button>
      </div>
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      {requests.length === 0 ? null : (
        <ul className="divide-y rounded-lg border" aria-live="polite">
          {requests.map((request) => (
            <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 p-3">
              <span className="text-sm">{describe(request)}</span>
              {request.kind === "export" && request.status === "ready" ? (
                <a
                  href={`${apiOrigin}/v1/me/data-requests/${request.id}/file`}
                  className="text-sm font-medium text-primary underline underline-offset-4"
                >
                  {text.download}
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
