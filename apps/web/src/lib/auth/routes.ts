import type { Route } from "next";

/**
 * The API's cookies (apps/api/src/app/core/cookies.py). The session cookie is HttpOnly: the web
 * server only checks that it's there and forwards it; the CSRF one the browser reads and echoes.
 */
export const SESSION_COOKIE = "__Secure-session";
export const CSRF_COOKIE = "__Secure-csrf";

export const SIGN_IN_PATH = "/sign-in" satisfies Route;
export const STAFF_SIGN_IN_PATH = "/staff/sign-in" satisfies Route;
export const ACCOUNT_PATH = "/account" satisfies Route;
export const STAFF_HOME_PATH = "/staff" satisfies Route;
export const OPS_HOME_PATH = "/ops" satisfies Route;
export const OPS_LISTINGS_PATH = "/ops/listings" satisfies Route;
export const OPS_NEW_LISTING_PATH = "/ops/listings/new" satisfies Route;

/** Areas only for signed-in people, and where each sends people who aren't. */
const PROTECTED_AREAS: readonly { prefix: Route; signIn: Route }[] = [
  { prefix: ACCOUNT_PATH, signIn: SIGN_IN_PATH },
  { prefix: STAFF_HOME_PATH, signIn: STAFF_SIGN_IN_PATH },
  { prefix: OPS_HOME_PATH, signIn: STAFF_SIGN_IN_PATH },
];
const SIGN_IN_PATHS: readonly string[] = [SIGN_IN_PATH, STAFF_SIGN_IN_PATH];

/** The sign-in page for `pathname`, if it is in a protected area (and isn't a sign-in page). */
export function signInPageFor(pathname: string): Route | undefined {
  if (SIGN_IN_PATHS.includes(pathname)) return undefined;
  return PROTECTED_AREAS.find(
    (area) => pathname === area.prefix || pathname.startsWith(`${area.prefix}/`),
  )?.signIn;
}

/** A sign-in page that sends people on to `next` once they're in. */
export function signInUrl(signIn: Route, next: string): Route {
  return `${signIn}?${new URLSearchParams({ next }).toString()}` as Route;
}

const MAX_NEXT_LENGTH = 512;

/**
 * Where a sign-in may send someone afterwards: a path on this site, never another site (an open
 * redirect would let a link to our sign-in page send people anywhere), and never back to a
 * sign-in page.
 */
export function safeNext(value: string | string[] | undefined, fallback: Route): Route {
  if (typeof value !== "string" || value.length > MAX_NEXT_LENGTH) return fallback;
  // One slash, then not a second one or a backslash: "//evil.example" and "/\evil.example" are
  // other sites to a browser. No whitespace or control characters either.
  if (!/^\/(?![/\\])[^\s\u0000-\u001f\u007f]*$/u.test(value)) return fallback;
  const pathname = value.split(/[?#]/u, 1)[0] ?? "";
  if (SIGN_IN_PATHS.includes(pathname)) return fallback;
  return value as Route;
}
