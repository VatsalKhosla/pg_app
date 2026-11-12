"use client";

import { Moon, Sun } from "lucide-react";

import { buttonVariants } from "@/components/ui/button-variants";

/** The cookie that remembers the choice, so the server draws the page in it (src/app/layout.tsx). */
export const THEME_COOKIE = "theme";
const YEAR_SECONDS = 31_536_000;

function nowDark(): boolean {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "dark" || chosen === "light") return chosen === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * Switches the whole site between light and dark, and remembers it. Until someone uses it, the
 * site follows the system. Both icons are drawn and CSS shows the right one, so the server and the
 * browser always agree.
 */
export function ThemeToggle({ label }: { label: string }) {
  function toggle() {
    const next = nowDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    document.cookie = `${THEME_COOKIE}=${next}; Path=/; Max-Age=${String(YEAR_SECONDS)}; SameSite=Lax; Secure`;
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={buttonVariants({ variant: "ghost", size: "icon", shape: "pill" })}
    >
      <Moon aria-hidden="true" className="dark:hidden" />
      <Sun aria-hidden="true" className="hidden dark:block" />
    </button>
  );
}
