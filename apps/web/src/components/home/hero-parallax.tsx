"use client";

import { useEffect, useRef } from "react";

/**
 * Lets the pointer move the evening scene's layers against each other, on desktops and only for
 * people who haven't asked for less motion. It writes two numbers to the hero's style; CSS does
 * the rest, a little further for the nearer layers.
 */
export function HeroParallax() {
  const anchor = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    const hero = anchor.current?.parentElement;
    if (!hero) return;
    const allowed = window.matchMedia(
      "(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)",
    );
    if (!allowed.matches) return;

    let frame = 0;
    const move = (event: PointerEvent) => {
      if (frame !== 0) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const box = hero.getBoundingClientRect();
        const x = (event.clientX - box.left) / box.width - 0.5;
        const y = (event.clientY - box.top) / box.height - 0.5;
        hero.style.setProperty("--px", x.toFixed(3));
        hero.style.setProperty("--py", y.toFixed(3));
      });
    };
    hero.addEventListener("pointermove", move, { passive: true });
    return () => {
      hero.removeEventListener("pointermove", move);
      cancelAnimationFrame(frame);
    };
  }, []);

  return <span ref={anchor} hidden />;
}
