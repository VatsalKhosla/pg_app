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
    <div className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center px-gutter py-16">
      <div className="space-y-4 rounded-[2rem] border bg-card p-6 text-card-foreground shadow-md sm:p-8">
        <h1 className="text-title-1 font-medium text-foreground">{title}</h1>
        <p className="text-lg text-muted-foreground">{body}</p>
        {detail === undefined ? null : (
          <p className="rounded-xl border border-border/80 bg-surface px-3.5 py-2 font-mono text-sm text-muted-foreground">
            {detail}
          </p>
        )}
        <div className="pt-2">{action}</div>
      </div>
    </div>
  );
}
