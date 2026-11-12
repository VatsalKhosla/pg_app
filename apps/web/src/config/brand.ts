/**
 * The only place the brand lives (CLAUDE.md): its name, which the founders chose on 2026-10-28,
 * and its colours: Golden hour (2026-11-08), brightened to dusk violet on 2026-11-12 at the founders' word that pages felt dull. Copy, including the tagline, lives
 * in the message files so it can be translated; facts about the company behind it live in
 * company.ts.
 *
 * Colours reach the CSS through `brandStyle` (custom properties on <html>), so components only use
 * the design tokens in globals.css. Each foreground keeps at least 4.5:1 contrast with its
 * background in both themes (WCAG 2.2 AA); tests/unit/brand-contrast.test.ts checks every pair.
 */
export const brand = {
  name: "Fix Your Stay",
  colors: {
    /** Dusk violet: the actions, and the page's character. In the dark theme, a soft lavender. */
    primary: "#5b2bb5",
    primaryForeground: "#ffffff",
    primaryDark: "#c9b3ff",
    primaryForegroundDark: "#1b0a3a",
    /** The marigold fill, for the one action that matters most on a screen. */
    sun: "#f6a623",
    sunForeground: "#231403",
    sunDark: "#f7b23e",
    sunForegroundDark: "#1c1203",
    /** A deep orange that reads as text on the light ground. */
    marigold: "#c2410c",
    marigoldDark: "#fdba74",
    /** Coral rose: warmth, and things that need a second look. */
    ember: "#be2550",
    emberDark: "#ff8fa3",
    /** Teal: the second Metro line, structure and calm. */
    dusk: "#0e7490",
    duskDark: "#67d4e8",
    /** Neem green: verified, safe, done. */
    neem: "#15803d",
    neemDark: "#6ee7a8",
    /** The evening band, which stays dark in both themes. */
    night: "#160f2b",
    nightDark: "#0b0716",
  },
  /** Page backgrounds, for the browser's theme colour; they match --background in globals.css. */
  surfaces: {
    light: "#faf8ff",
    dark: "#0f0b1c",
  },
} as const;

/** The brand colours as CSS custom properties, set on <html> by the root layout. */
export const brandStyle = {
  "--brand-primary": brand.colors.primary,
  "--brand-primary-foreground": brand.colors.primaryForeground,
  "--brand-primary-dark": brand.colors.primaryDark,
  "--brand-primary-foreground-dark": brand.colors.primaryForegroundDark,
  "--brand-sun": brand.colors.sun,
  "--brand-sun-foreground": brand.colors.sunForeground,
  "--brand-sun-dark": brand.colors.sunDark,
  "--brand-sun-foreground-dark": brand.colors.sunForegroundDark,
  "--brand-marigold": brand.colors.marigold,
  "--brand-marigold-dark": brand.colors.marigoldDark,
  "--brand-ember": brand.colors.ember,
  "--brand-ember-dark": brand.colors.emberDark,
  "--brand-dusk": brand.colors.dusk,
  "--brand-dusk-dark": brand.colors.duskDark,
  "--brand-neem": brand.colors.neem,
  "--brand-neem-dark": brand.colors.neemDark,
  "--brand-night": brand.colors.night,
  "--brand-night-dark": brand.colors.nightDark,
} as const;

/** The letter on the brand mark and the app icons. */
export const brandInitial = brand.name.charAt(0).toUpperCase();
