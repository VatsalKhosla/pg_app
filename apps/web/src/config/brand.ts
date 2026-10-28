/**
 * The only place the brand lives (CLAUDE.md): its name and colours. The founders haven't chosen a
 * name yet, so this stays a placeholder until they do. Copy, including the tagline, lives in the
 * message files so it can be translated.
 *
 * Colours reach the CSS through `brandStyle` (custom properties on <html>), so components only use
 * the design tokens in globals.css. Each foreground keeps at least 4.5:1 contrast with its
 * background (WCAG 2.2 AA): white on primary is 6.2:1, and the dark-mode pair is 7.4:1.
 */
export const brand = {
  name: "Fix Your Stay",
  colors: {
    primary: "#0e6b74",
    primaryForeground: "#ffffff",
    primaryDark: "#5ec4cc",
    primaryForegroundDark: "#062a2e",
  },
  /** Page backgrounds, for the browser's theme colour; they match --background in globals.css. */
  surfaces: {
    light: "#ffffff",
    dark: "#0f0f0f",
  },
} as const;

/** The brand colours as CSS custom properties, set on <html> by the root layout. */
export const brandStyle = {
  "--brand-primary": brand.colors.primary,
  "--brand-primary-foreground": brand.colors.primaryForeground,
  "--brand-primary-dark": brand.colors.primaryDark,
  "--brand-primary-foreground-dark": brand.colors.primaryForegroundDark,
} as const;

/** The letter on the brand mark and the app icons. */
export const brandInitial = brand.name.charAt(0).toUpperCase();
