/**
 * Public configuration, inlined into the bundle at build time. Only values that are safe in a
 * browser belong here (CLAUDE.md): anything prefixed NEXT_PUBLIC_ is readable by anyone.
 */

const environments = ["local", "test", "staging", "production"] as const;

/** Where this build runs; the same names as the API's APP_ENV. */
export type AppEnvironment = (typeof environments)[number];

function isAppEnvironment(value: string): value is AppEnvironment {
  return (environments as readonly string[]).includes(value);
}

function parseEnvironment(value: string | undefined): AppEnvironment {
  const environment = value === undefined || value === "" ? "local" : value;
  if (!isAppEnvironment(environment)) {
    throw new Error(`NEXT_PUBLIC_APP_ENV must be one of ${environments.join(", ")}`);
  }
  return environment;
}

/** `value` as an absolute URL, or `fallback` when it's unset. */
export function parseUrl(name: string, value: string | undefined, fallback: string): URL {
  try {
    return new URL(value === undefined || value === "" ? fallback : value);
  } catch {
    throw new Error(`${name} must be an absolute URL`);
  }
}

function optional(value: string | undefined): string | undefined {
  return value === undefined || value === "" ? undefined : value;
}

/** Raster map tiles and the credit their licence requires. */
export interface MapTiles {
  /** A {z}/{x}/{y} template for 256 px tiles. */
  url: string;
  /** HTML for the map's corner. */
  attribution: string;
}

/** OpenStreetMap's own tile servers: fine for development, too light for a live site. */
export const OSM_TILES: MapTiles = {
  url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution:
    '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (character) => `&#${String(character.charCodeAt(0))};`);
}

/**
 * The pin picker's tiles. OpenStreetMap's servers are for light use only (their tile policy), so
 * they're the default for local development alone; a deployed site names its provider's tiles,
 * with the credit their terms ask for, or gets no map (coordinates and GPS only).
 */
export function parseMapTiles(
  url: string | undefined,
  attribution: string | undefined,
  environment: AppEnvironment,
): MapTiles | undefined {
  if (url === undefined) return environment === "local" ? OSM_TILES : undefined;
  if (
    !/^https:\/\/[^\s]+$/u.test(url) ||
    !["{z}", "{x}", "{y}"].every((part) => url.includes(part))
  ) {
    throw new Error("NEXT_PUBLIC_MAP_TILES_URL must be an https:// template with {z}, {x} and {y}");
  }
  if (attribution === undefined) {
    throw new Error("NEXT_PUBLIC_MAP_TILES_ATTRIBUTION must credit the tiles, as their terms ask");
  }
  return { url, attribution: escapeHtml(attribution) };
}

const appEnv = parseEnvironment(process.env.NEXT_PUBLIC_APP_ENV);

// Each variable is written out in full: Next.js inlines only literal process.env.NEXT_PUBLIC_*.
export const publicEnv = {
  appEnv,
  siteUrl: parseUrl(
    "NEXT_PUBLIC_SITE_URL",
    process.env.NEXT_PUBLIC_SITE_URL,
    "http://localhost:3000",
  ),
  /**
   * The API, as the browser reaches it. It must be on the same site as siteUrl (localhost with
   * localhost, or sibling subdomains when deployed), or the browser keeps the API's session cookie
   * from the web server.
   */
  apiUrl: parseUrl("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL, "http://localhost:8000"),
  /** Browser error reporting; Sentry stays off while this is empty. */
  sentryDsn: optional(process.env.NEXT_PUBLIC_SENTRY_DSN),
  /**
   * Cloudflare Turnstile's site key for the sign-in form. Without it there is no widget (local
   * development and tests, where the API checks nothing either).
   */
  turnstileSiteKey: optional(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY),
  /** Where listing photos are read from: the CDN when deployed, the public bucket locally. */
  mediaUrl: parseUrl(
    "NEXT_PUBLIC_MEDIA_URL",
    process.env.NEXT_PUBLIC_MEDIA_URL,
    "http://127.0.0.1:8333/pg-platform-media",
  ),
  /** Where the browser posts uploads: the private bucket's storage (ADR 0022). */
  uploadOrigin: parseUrl(
    "NEXT_PUBLIC_UPLOAD_ORIGIN",
    process.env.NEXT_PUBLIC_UPLOAD_ORIGIN,
    "http://127.0.0.1:8333",
  ),
  /** The ops pin picker's map tiles, if it gets a map (see parseMapTiles). */
  mapTiles: parseMapTiles(
    optional(process.env.NEXT_PUBLIC_MAP_TILES_URL),
    optional(process.env.NEXT_PUBLIC_MAP_TILES_ATTRIBUTION),
    appEnv,
  ),
} as const;
