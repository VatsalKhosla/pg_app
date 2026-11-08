/**
 * The only place the brand lives (CLAUDE.md): its name, which the founders chose on 2026-10-28,
 * and its colours, Golden hour, which they chose on 2026-11-08. Copy, including the tagline, lives
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
    /** Deep ink: the actions, and the page's weight. In the dark theme, marigold takes this role. */
    primary: "#1e2b45",
    primaryForeground: "#ffffff",
    primaryDark: "#f2b24c",
    primaryForegroundDark: "#1a1204",
    /** The marigold fill, for the one action that matters most on a screen. */
    sun: "#f0a93b",
    sunForeground: "#1e1405",
    sunDark: "#f2b24c",
    sunForegroundDark: "#1a1204",
    /** Marigold deep enough to read as text on ivory. */
    marigold: "#a55f00",
    marigoldDark: "#f5c46e",
    /** The last of the sunset: warmth, and things that need a second look. */
    ember: "#b2431f",
    emberDark: "#ff9d7d",
    /** Blue-grey dusk: structure, policies and protection. */
    dusk: "#34466f",
    duskDark: "#a9bbe3",
    /** Neem green: verified, safe, done. */
    neem: "#256b4c",
    neemDark: "#7cd3a6",
    /** The evening band, which stays dark in both themes. */
    night: "#121827",
    nightDark: "#080b11",
  },
  /** Page backgrounds, for the browser's theme colour; they match --background in globals.css. */
  surfaces: {
    light: "#fbf8f2",
    dark: "#0d1119",
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
