import type * as React from "react";

/** The body of the error and not-found pages: a heading, a sentence and what to do next. */
export function ErrorMessage({
  title,
  body,
  detail,
  action,
}: {
  title: string;
  body: string;
  detail?: string | undefined;
  action: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-start justify-center gap-4 px-4 py-16 sm:px-6">
      <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
      <p className="text-lg text-muted-foreground">{body}</p>
      {detail === undefined ? null : (
        <p className="font-mono text-sm text-muted-foreground">{detail}</p>
      )}
      <div className="mt-2">{action}</div>
    </div>
  );
}
