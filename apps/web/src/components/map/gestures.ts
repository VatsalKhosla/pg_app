/**
 * How the maps take gestures and move, the same with either adapter (ADR 0069).
 *
 * - With a mouse or trackpad, the wheel zooms the map straight away: no Ctrl or ⌘ to hold.
 * - On a touch screen, a map inside a page leaves one finger to the page's scrolling and moves
 *   with two, so nobody gets stuck on it on the way down the page.
 * - The search map fills its screen, so there is no page to scroll past it: one finger moves it.
 * - Anyone who asks their device for less motion gets every move at once, without an animation.
 */

/** Whether the map shares the screen with a page that scrolls past it. */
export type MapPlacement = "fills-screen" | "in-page";

/** Whether the person points with a mouse or trackpad rather than a finger. */
export function pointsFinely(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(pointer: fine)").matches;
}

/** Whether one finger should scroll the page and two move the map. */
export function cooperative(placement: MapPlacement, finePointer = pointsFinely()): boolean {
  return placement === "in-page" && !finePointer;
}

/** Whether moves should happen at once: the person asked for less motion. */
export function prefersStillness(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}
