import type { ReactNode } from "react";

/** The page's closing invitation, on an evening field. */
export function CtaBand({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby="cta-title"
      className="scope-night relative isolate mx-gutter overflow-hidden rounded-[2rem] sm:rounded-[3rem]"
    >
      <div aria-hidden="true" className="sky-band absolute inset-0 -z-10 opacity-90" />
      <div className="mx-auto flex max-w-page flex-col items-start gap-5 px-6 py-14 sm:px-12 sm:py-20 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-2xl">
          <h2 id="cta-title" className="text-display font-medium">
            {title}
          </h2>
          <p className="mt-3 text-lg text-night-foreground">{body}</p>
        </div>
        <div className="flex flex-wrap gap-3">{children}</div>
      </div>
    </section>
  );
}
