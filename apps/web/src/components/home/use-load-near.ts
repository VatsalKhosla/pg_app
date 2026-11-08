"use client";

import { type ComponentType, useEffect, useRef, useState } from "react";

/**
 * Loads a component's code once its place on the page comes within `margin` of the screen, so the
 * first screen doesn't pay for what's further down (ADR 0066). Until then the caller shows what the
 * server drew. Nothing swaps in if the code fails to load.
 */
export function useLoadNear<Props>(
  load: () => Promise<ComponentType<Props>>,
  margin = "400px",
): { ref: React.RefObject<HTMLDivElement | null>; Loaded: ComponentType<Props> | null } {
  const ref = useRef<HTMLDivElement | null>(null);
  const [Loaded, setLoaded] = useState<ComponentType<Props> | null>(null);
  const loader = useRef(load);

  useEffect(() => {
    const element = ref.current;
    if (element === null) return;
    let alive = true;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        loader
          .current()
          .then((component) => {
            if (alive) setLoaded(() => component);
          })
          .catch(() => undefined);
      },
      { rootMargin: margin },
    );
    observer.observe(element);
    return () => {
      alive = false;
      observer.disconnect();
    };
  }, [margin]);

  return { ref, Loaded };
}
