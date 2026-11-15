"use client";

import { Minus, Plus } from "lucide-react";

const buttonClasses =
  "grid size-[29px] place-items-center text-foreground outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent";

/**
 * The Google maps' zoom buttons, in the page's words and look: Google's own control can't take
 * the site's labels, nor sit below the search page's floating header. They stand where
 * MapLibre's do, top right.
 */
export function ZoomButtons({
  onZoom,
  atMin,
  atMax,
  text,
  className = "top-2.5",
}: {
  onZoom: (step: 1 | -1) => void;
  atMin: boolean;
  atMax: boolean;
  text: { zoomIn: string; zoomOut: string };
  /** Where the buttons sit from the top. */
  className?: string;
}) {
  return (
    <div
      className={`absolute right-2.5 z-10 flex flex-col overflow-hidden rounded-[4px] bg-background shadow-[0_0_0_2px_rgb(0_0_0/10%)] ${className}`}
    >
      <button
        type="button"
        aria-label={text.zoomIn}
        title={text.zoomIn}
        disabled={atMax}
        onClick={() => {
          onZoom(1);
        }}
        className={buttonClasses}
      >
        <Plus aria-hidden="true" className="size-4" />
      </button>
      <button
        type="button"
        aria-label={text.zoomOut}
        title={text.zoomOut}
        disabled={atMin}
        onClick={() => {
          onZoom(-1);
        }}
        className={`border-t ${buttonClasses}`}
      >
        <Minus aria-hidden="true" className="size-4" />
      </button>
    </div>
  );
}
