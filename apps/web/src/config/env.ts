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

// Each variable is written out in full: Next.js inlines only literal process.env.NEXT_PUBLIC_*.
export const publicEnv = {
  appEnv: parseEnvironment(process.env.NEXT_PUBLIC_APP_ENV),
  siteUrl: parseUrl(
    "NEXT_PUBLIC_SITE_URL",
    process.env.NEXT_PUBLIC_SITE_URL,
    "http://localhost:3000",
  ),
  apiUrl: parseUrl("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL, "http://127.0.0.1:8000"),
  /** Browser error reporting; Sentry stays off while this is empty. */
  sentryDsn: optional(process.env.NEXT_PUBLIC_SENTRY_DSN),
} as const;
