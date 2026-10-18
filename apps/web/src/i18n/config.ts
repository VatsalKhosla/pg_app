/**
 * Locales the site speaks. English (India) only for now; Hindi comes later (ARCHITECTURE §16), and
 * with it locale detection and localised routes. en-IN also gives Indian number grouping.
 */
export const locales = ["en-IN"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en-IN";

/** Dates and times show in India's time zone wherever the reader is (CLAUDE.md). */
export const timeZone = "Asia/Kolkata";
