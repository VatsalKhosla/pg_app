/**
 * What the browser needs to know about Sentry, derived from the public DSN
 * (`https://<public key>@<host>[/<path>]/<project id>`): the origin it sends events to, which the
 * Content Security Policy must allow, and the security endpoint that collects CSP violation
 * reports (https://docs.sentry.io/platforms/dotnet/security-policy-reporting/).
 */
export interface SentryEndpoints {
  origin: string;
  securityReportUrl: string;
}

export function sentryEndpoints(dsn: string, environment: string): SentryEndpoints {
  let url: URL;
  try {
    url = new URL(dsn);
  } catch {
    throw new Error("NEXT_PUBLIC_SENTRY_DSN is not a URL");
  }
  const segments = url.pathname.split("/").filter((segment) => segment !== "");
  const projectId = segments.pop();
  if (url.username === "" || projectId === undefined || !/^\d+$/.test(projectId)) {
    throw new Error("NEXT_PUBLIC_SENTRY_DSN must look like https://<key>@<host>/<project id>");
  }
  const prefix = segments.map((segment) => `/${segment}`).join("");
  const report = new URL(`${url.origin}${prefix}/api/${projectId}/security/`);
  report.searchParams.set("sentry_key", url.username);
  report.searchParams.set("sentry_environment", environment);
  return { origin: url.origin, securityReportUrl: report.href };
}
