// Keys Google's map moves with while it has focus.
const MOVE_KEYS = new Set([
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "+",
  "-",
  "=",
  "_",
  "PageUp",
  "PageDown",
  "Home",
  "End",
]);
// A move that starts this soon after the person's input is theirs.
const INPUT_MS = 600;

/**
 * Tells the person's moves from the page's (MapViewProps.onBoundsChange). Google's events don't
 * say who moved the map, as MapLibre's do, so this watches for the person's hand on it: a press
 * held, the wheel, or a key that moves it, just before or while the map moves. A drag counts
 * whenever it happens. Any of them also stops a glide the page started, so the map never fights
 * the person for the camera.
 */
export class PersonWatch {
  private pressed = false;
  private inputAt = Number.NEGATIVE_INFINITY;
  private moved = false;
  private readonly stopListening: () => void;

  constructor(container: HTMLElement, onHand: () => void) {
    const input = () => {
      this.inputAt = performance.now();
      onHand();
    };
    const press = () => {
      this.pressed = true;
      input();
    };
    const release = () => {
      if (!this.pressed) return;
      this.pressed = false;
      this.inputAt = performance.now();
    };
    const key = (event: KeyboardEvent) => {
      if (MOVE_KEYS.has(event.key)) input();
    };
    const options = { capture: true, passive: true } as const;
    container.addEventListener("pointerdown", press, options);
    container.addEventListener("wheel", input, options);
    container.addEventListener("keydown", key, options);
    window.addEventListener("pointerup", release, options);
    window.addEventListener("pointercancel", release, options);
    this.stopListening = () => {
      container.removeEventListener("pointerdown", press, options);
      container.removeEventListener("wheel", input, options);
      container.removeEventListener("keydown", key, options);
      window.removeEventListener("pointerup", release, options);
      window.removeEventListener("pointercancel", release, options);
    };
  }

  /** The map moved: the person's move if their hand is on it, or just was. */
  onMove(): void {
    if (this.pressed || performance.now() - this.inputAt < INPUT_MS) this.moved = true;
  }

  /** The person moved it some other way: a drag, a cluster, a zoom button. */
  mark(): void {
    this.moved = true;
  }

  /** Whether the person moved the map since it last came to rest; and starts afresh. */
  take(): boolean {
    const moved = this.moved;
    this.moved = false;
    return moved;
  }

  dispose(): void {
    this.stopListening();
  }
}
