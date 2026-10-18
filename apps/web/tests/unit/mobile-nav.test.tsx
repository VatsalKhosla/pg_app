import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { MobileNav } from "@/components/layout/mobile-nav";
import type { NavigationLink } from "@/components/layout/navigation";

import { WCAG_22_AA } from "../wcag";

// next/link needs the app router, which a component test doesn't have; a plain link is enough
// here. Real navigation is covered by the browser tests.
vi.mock("next/link", () => ({
  default: ({ href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props} />,
}));

const labels = {
  openMenu: "Open menu",
  closeMenu: "Close menu",
  menuTitle: "Menu",
  mainNavigation: "Main",
};

const links: NavigationLink[] = [
  { href: "/#how-it-works", targetId: "how-it-works", label: "How it works" },
  { href: "/#owners", targetId: "owners", label: "PG owners" },
];

function renderNav() {
  render(
    <>
      <MobileNav labels={labels} links={links} />
      <section id="owners" tabIndex={-1}>
        Owners
      </section>
    </>,
  );
  return screen.getByRole("button", { name: "Open menu" });
}

/** Open the menu the way a person would: focus the button, then press it. */
async function openMenu(button: HTMLElement): Promise<HTMLElement> {
  button.focus();
  fireEvent.click(button);
  // The menu loads on first use.
  return screen.findByRole("dialog", { name: "Menu" });
}

async function wcagViolations(): Promise<string[]> {
  const results = await axe.run(document.body, { runOnly: { type: "tag", values: WCAG_22_AA } });
  return results.violations.map((violation) => `${violation.id}: ${violation.help}`);
}

describe("MobileNav", () => {
  it("renders only the button until the menu is wanted", () => {
    const button = renderNav();

    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.getAttribute("aria-haspopup")).toBe("dialog");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens a labelled menu with the main navigation", async () => {
    const button = renderNav();

    const dialog = await openMenu(button);

    const items = screen
      .getAllByRole("link")
      .map((link) => [link.textContent, link.getAttribute("href")]);
    expect(dialog.querySelector("nav")?.getAttribute("aria-label")).toBe("Main");
    expect(items).toEqual([
      ["How it works", "/#how-it-works"],
      ["PG owners", "/#owners"],
    ]);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(await wcagViolations()).toEqual([]);
  });

  // Radix moves focus once the dialog has unmounted, on a timer, hence waitFor.
  it("closes on Escape and returns focus to the menu button", async () => {
    const button = renderNav();

    fireEvent.keyDown(await openMenu(button), { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => {
      expect(document.activeElement).toBe(button);
    });
  });

  it("closes when a link is followed and moves focus to the section it lands on", async () => {
    const button = renderNav();

    await openMenu(button);
    fireEvent.click(screen.getByRole("link", { name: "PG owners" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => {
      expect(document.activeElement).toBe(document.getElementById("owners"));
    });
  });
});
