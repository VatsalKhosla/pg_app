"use client";

import { type ReactNode, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export type SheetSnap = "peek" | "half" | "full";

// The peek shows the handle and the results' count; full leaves a strip of map above it.
const PEEK_PX = 112;
const FULL_GAP_PX = 24;
// A press that moves less than this is a tap on the handle, not a drag.
const TAP_SLOP_PX = 6;

const heights: Record<SheetSnap, string> = {
  peek: "h-28",
  half: "h-1/2",
  full: "h-[calc(100%-1.5rem)]",
};

function snapHeights(container: number): Record<SheetSnap, number> {
  return { peek: PEEK_PX, half: container / 2, full: container - FULL_GAP_PX };
}

/** The snap nearest a height the sheet was dragged to. */
export function nearestSnap(height: number, container: number): SheetSnap {
  const options = snapHeights(container);
  let best: SheetSnap = "peek";
  for (const snap of ["half", "full"] as const) {
    if (Math.abs(options[snap] - height) < Math.abs(options[best] - height)) best = snap;
  }
  return best;
}

/** One step up, peek to half to full; from full, back down to peek. */
export function nextSnap(snap: SheetSnap): SheetSnap {
  switch (snap) {
    case "peek":
      return "half";
    case "half":
      return "full";
    case "full":
      return "peek";
  }
}

/**
 * The phone's list over the map (BUILD_PLAN 3.5): dragged by its handle to a peek, half the
 * screen or nearly all of it. Dragging isn't needed (WCAG 2.2 2.5.7): tapping the handle, which
 * is a button, steps through the same heights, and tabbing into a peeking list opens it.
 */
export function BottomSheet({
  snap,
  onSnapChange,
  label,
  moreLabel,
  lessLabel,
  children,
}: {
  snap: SheetSnap;
  onSnapChange: (snap: SheetSnap) => void;
  /** The list's name, for screen readers. */
  label: string;
  moreLabel: string;
  lessLabel: string;
  children: ReactNode;
}) {
  const sheetRef = useRef<HTMLElement>(null);
  const dragRef = useRef<{ startY: number; startHeight: number; moved: boolean } | null>(null);
  const [dragHeight, setDragHeight] = useState<number | null>(null);

  const containerHeight = () => sheetRef.current?.parentElement?.clientHeight ?? window.innerHeight;

  return (
    <section
      ref={sheetRef}
      aria-label={label}
      onFocus={() => {
        if (snap === "peek") onSnapChange("half");
      }}
      style={dragHeight === null ? undefined : { height: `${String(dragHeight)}px` }}
      className={cn(
        "absolute inset-x-0 bottom-0 z-10 flex flex-col rounded-t-2xl border-t bg-background shadow-[0_-4px_16px_rgb(0_0_0/0.12)]",
        dragHeight === null && "motion-safe:transition-[height] motion-safe:duration-200",
        heights[snap],
      )}
    >
      <button
        type="button"
        aria-label={snap === "full" ? lessLabel : moreLabel}
        aria-expanded={snap !== "peek"}
        className="flex h-8 w-full shrink-0 touch-none cursor-grab items-center justify-center rounded-t-2xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 active:cursor-grabbing"
        onFocus={(event) => {
          // The handle itself doesn't open the list: its press does.
          event.stopPropagation();
        }}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          dragRef.current = {
            startY: event.clientY,
            startHeight: sheetRef.current?.offsetHeight ?? PEEK_PX,
            moved: false,
          };
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current;
          if (drag === null) return;
          const delta = drag.startY - event.clientY;
          if (!drag.moved && Math.abs(delta) < TAP_SLOP_PX) return;
          drag.moved = true;
          const { peek, full } = snapHeights(containerHeight());
          setDragHeight(Math.min(full, Math.max(peek, drag.startHeight + delta)));
        }}
        onPointerUp={(event) => {
          const drag = dragRef.current;
          if (drag?.moved !== true) return;
          const delta = drag.startY - event.clientY;
          onSnapChange(nearestSnap(drag.startHeight + delta, containerHeight()));
          setDragHeight(null);
        }}
        onPointerCancel={() => {
          dragRef.current = null;
          setDragHeight(null);
        }}
        onClick={() => {
          // A drag ends in a click too; only a tap steps.
          if (dragRef.current?.moved === true) {
            dragRef.current = null;
            return;
          }
          dragRef.current = null;
          onSnapChange(nextSnap(snap));
        }}
      >
        <span aria-hidden="true" className="h-1.5 w-10 rounded-full bg-muted-foreground/40" />
      </button>
      <div
        className={cn(
          "min-h-0 flex-1 overscroll-contain px-4 pb-4",
          snap === "peek" && dragHeight === null ? "overflow-hidden" : "overflow-y-auto",
        )}
      >
        {children}
      </div>
    </section>
  );
}
