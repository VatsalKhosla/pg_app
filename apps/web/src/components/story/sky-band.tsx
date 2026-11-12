import type { ReactNode } from "react";

import { scene } from "@/components/home/scene-geometry";

/**
 * A page's opening band: the home page's evening in miniature (a dusk sky, the sun low over a
 * skyline), with the page's title and what it's for. It runs under the floating header, as the
 * home page's hero does. Drawn on the server; it moves for nobody.
 */
export function SkyBand({
  title,
  intro,
  children,
}: {
  title: string;
  intro: string;
  children?: ReactNode;
}) {
  return (
    <header className="scope-night relative isolate -mt-[4.75rem] overflow-hidden rounded-b-[2rem] pt-[4.75rem] sm:rounded-b-[3.5rem]">
      <div aria-hidden="true" className="sky-band absolute inset-0 -z-10" />
      <div aria-hidden="true" className="sky-sun absolute -z-10" />
      <svg
        aria-hidden="true"
        focusable="false"
        viewBox="0 0 1600 500"
        preserveAspectRatio="xMidYMax slice"
        className="sky-skyline absolute inset-x-0 bottom-0 -z-10 h-28 w-full sm:h-36"
      >
        <path d={scene.far} />
      </svg>
      <div className="mx-auto max-w-page px-gutter pt-14 pb-24 sm:pt-20 sm:pb-32">
        <h1 className="max-w-[18ch] text-hero font-medium">{title}</h1>
        <p className="mt-5 max-w-[40rem] text-lg leading-relaxed text-night-foreground sm:text-xl">
          {intro}
        </p>
        {children === undefined ? null : (
          <div className="mt-8 flex flex-wrap gap-3">{children}</div>
        )}
      </div>
    </header>
  );
}
