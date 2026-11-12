import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { brand } from "@/config/brand";

// WCAG 2.2 AA for the palette: text 4.5:1 on what it sits on, control borders and focus rings 3:1.

function luminance(hex: string): number {
  const channel = (start: number) => {
    const c = parseInt(hex.slice(start, start + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const rootBlock = css.slice(css.indexOf(":root {"), css.indexOf(":root[data-theme"));

/** Each token written as light-dark(#light, #dark), or one colour for both. */
function tokens(which: 0 | 1): Record<string, string> {
  const found: Record<string, string> = {};
  for (const match of rootBlock.matchAll(
    /--([a-z-]+):\s*light-dark\((#[0-9a-f]{6}),\s*(#[0-9a-f]{6})\);/g,
  )) {
    found[match[1] ?? ""] = (which === 0 ? match[2] : match[3]) ?? "";
  }
  for (const match of rootBlock.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6});/g)) {
    found[match[1] ?? ""] = match[2] ?? "";
  }
  return found;
}

function colour(theme: Record<string, string>, name: string): string {
  const value = theme[name];
  if (value === undefined) throw new Error(`No token called ${name}`);
  return value;
}

const c = brand.colors;
const light: Record<string, string> = {
  ...tokens(0),
  primary: c.primary,
  "primary-foreground": c.primaryForeground,
  sun: c.sun,
  "sun-foreground": c.sunForeground,
  marigold: c.marigold,
  ember: c.ember,
  dusk: c.dusk,
  neem: c.neem,
  night: c.night,
  "night-raised": "#231a40",
};
const dark: Record<string, string> = {
  ...tokens(1),
  primary: c.primaryDark,
  "primary-foreground": c.primaryForegroundDark,
  sun: c.sunDark,
  "sun-foreground": c.sunForegroundDark,
  marigold: c.marigoldDark,
  ember: c.emberDark,
  dusk: c.duskDark,
  neem: c.neemDark,
  night: c.nightDark,
  "night-raised": "#160f29",
};

const text: readonly (readonly [string, string])[] = [
  ["foreground", "background"],
  ["foreground", "surface"],
  ["foreground", "surface-warm"],
  ["foreground", "card"],
  ["muted-foreground", "background"],
  ["muted-foreground", "surface"],
  ["muted-foreground", "surface-warm"],
  ["muted-foreground", "muted"],
  ["muted-foreground", "card"],
  ["primary-foreground", "primary"],
  ["primary", "background"],
  ["primary", "card"],
  ["sun-foreground", "sun"],
  ["marigold", "background"],
  ["marigold", "card"],
  ["ember", "background"],
  ["dusk", "background"],
  ["neem", "background"],
  ["ember-soft-foreground", "ember-soft"],
  ["marigold-soft-foreground", "marigold-soft"],
  ["dusk-soft-foreground", "dusk-soft"],
  ["neem-soft-foreground", "neem-soft"],
  ["destructive-foreground", "destructive"],
  ["destructive", "background"],
  ["destructive-soft-foreground", "destructive-soft"],
  ["success", "background"],
  ["success-soft-foreground", "success-soft"],
  ["warning-soft-foreground", "warning-soft"],
  ["night-foreground", "night"],
  ["night-muted", "night"],
  ["night-accent", "night"],
  ["night-foreground", "night-raised"],
  ["night-muted", "night-raised"],
];

describe.each([
  ["light", light],
  ["dark", dark],
] as const)("the %s theme", (_name, theme) => {
  it.each(text)("%s reads on %s at 4.5:1 or more", (fg, bg) => {
    expect(contrast(colour(theme, fg), colour(theme, bg))).toBeGreaterThanOrEqual(4.5);
  });
});

const lightInput = /--input:\s*light-dark\((#[0-9a-f]{6})/u.exec(rootBlock)?.[1] ?? "";

describe("controls in the light theme", () => {
  it.each(["background", "surface", "card"])("the control border keeps 3:1 on %s", (bg) => {
    expect(contrast(lightInput, colour(light, bg))).toBeGreaterThanOrEqual(3);
  });
});
