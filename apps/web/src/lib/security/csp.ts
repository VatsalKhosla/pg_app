/**
 * The Content Security Policy (ARCHITECTURE §17), built per request by src/proxy.ts.
 *
 * Scripts are strict: only those carrying the request's nonce run, plus whatever they load
 * ('strict-dynamic'); no 'unsafe-inline'. Next.js puts the nonce on its own scripts. Styles allow
 * inline because Radix (scroll locking), Google Maps (step 3.5) and server-rendered style
 * attributes add styles that can't carry a nonce. Injected CSS can't reach other sites either:
 * images, fonts and connections are limited to this site and the API (docs/adr/0011).
 */

/** The reporting group that `report-to` names; the proxy maps it to a URL. */
export const CSP_REPORT_GROUP = "csp-endpoint";

export interface CspOptions {
  nonce: string;
  /** `next dev` needs 'unsafe-eval' for React's debugging; production never does. */
  isDevelopment: boolean;
  /** Only on HTTPS sites; on http://localhost it would break local production runs. */
  upgradeInsecureRequests: boolean;
  /** Origins the browser may call besides its own: the API, error reporting. */
  connectOrigins: readonly string[];
  /** Where browsers report violations (Sentry's security endpoint), if anywhere. */
  reportUrl?: string | undefined;
}

export function buildContentSecurityPolicy(options: CspOptions): string {
  const directives: string[][] = [
    ["default-src", "'self'"],
    [
      "script-src",
      "'self'",
      `'nonce-${options.nonce}'`,
      "'strict-dynamic'",
      ...(options.isDevelopment ? ["'unsafe-eval'"] : []),
    ],
    ["style-src", "'self'", "'unsafe-inline'"],
    ["img-src", "'self'", "data:", "blob:"],
    ["font-src", "'self'"],
    ["connect-src", "'self'", ...options.connectOrigins],
    ["frame-src", "'none'"],
    ["worker-src", "'self'", "blob:"],
    ["manifest-src", "'self'"],
    ["object-src", "'none'"],
    ["base-uri", "'self'"],
    ["form-action", "'self'"],
    ["frame-ancestors", "'none'"],
  ];
  if (options.upgradeInsecureRequests) {
    directives.push(["upgrade-insecure-requests"]);
  }
  if (options.reportUrl !== undefined) {
    // report-uri for browsers without the Reporting API; report-to (via the Reporting-Endpoints
    // header) for the rest.
    directives.push(["report-uri", options.reportUrl], ["report-to", CSP_REPORT_GROUP]);
  }
  return directives.map((directive) => directive.join(" ")).join("; ");
}

/** The Reporting-Endpoints header value that backs `report-to`. */
export function reportingEndpoints(reportUrl: string): string {
  return `${CSP_REPORT_GROUP}="${reportUrl}"`;
}

/** A fresh, unguessable nonce: 128 random bits, base64-encoded. */
export function newNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}
