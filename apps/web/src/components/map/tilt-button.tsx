"use client";

import { Rotate3d } from "lucide-react";

/**
 * The search map's desktop button that tips the map back for depth, and lays it flat again. On a
 * phone the map keeps every pixel flat and readable, so the button shows from 1024 px only.
 */
export function TiltButton({
  tilted,
  onToggle,
  text,
}: {
  tilted: boolean;
  onToggle: () => void;
  text: { tilt: string; flatten: string };
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={tilted}
      aria-label={tilted ? text.flatten : text.tilt}
      title={tilted ? text.flatten : text.tilt}
      className="absolute top-[10.5rem] right-2.5 z-10 hidden size-[29px] place-items-center rounded-[4px] bg-background text-foreground shadow-[0_0_0_2px_rgb(0_0_0/10%)] outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring aria-pressed:bg-primary aria-pressed:text-primary-foreground lg:grid"
    >
      <Rotate3d aria-hidden="true" className="size-4" />
    </button>
  );
}
