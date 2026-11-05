import path from "node:path";

import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Security headers that are the same on every response (ARCHITECTURE §17). The Content Security
// Policy is per request, with a nonce, so src/proxy.ts sets it.
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  // Location only for this site's own "near me" search; nothing else.
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)",
  },
];

// Only where a student pays (ADR 0056). Razorpay's checkout asks for the payment feature in its
// frame, and a bank's page may open in a popup that has to report back to it.
const paymentPageHeaders = [
  { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
  {
    key: "Permissions-Policy",
    value:
      'camera=(), microphone=(), payment=(self "https://api.razorpay.com"), usb=(), geolocation=(self)',
  },
];

// The container image (apps/web/Dockerfile) builds Next.js's standalone server, traced from the
// repository's root so the workspace's API client comes along. Vercel builds need neither.
const standalone = process.env.NEXT_OUTPUT === "standalone";
// A site that serves the API at its own address (ADR 0055): `/v1/...` here is the API. It's for a
// test site on a host that can't share cookies with the API's, such as two onrender.com addresses,
// which browsers treat as separate sites. The browser then talks only to this site, so sign-in's
// cookies are first-party and there's nothing for CORS to allow, whatever address the site is on.
// Read while building: Next.js writes its rewrites into the build.
const apiProxyTarget = (process.env.API_PROXY_TARGET ?? "").replace(/\/+$/u, "");
// How long the API may take to answer through this site, when it may be asleep.
const apiWaitMs = Number(process.env.NEXT_PUBLIC_API_WAIT_MS ?? "") || undefined;

const nextConfig: NextConfig = {
  ...(standalone && {
    output: "standalone" as const,
    outputFileTracingRoot: path.join(process.cwd(), "..", ".."),
  }),
  poweredByHeader: false,
  reactStrictMode: true,
  typedRoutes: true,
  // The generated API client ships as TypeScript source.
  transpilePackages: ["@pg-platform/api-client"],
  experimental: {
    // radix-ui re-exports every primitive from one entry point, and webpack kept them all (about
    // 60 KB gzipped on every page) for the two this app uses; this imports each one directly.
    optimizePackageImports: ["radix-ui"],
    ...(apiWaitMs !== undefined && { proxyTimeout: apiWaitMs }),
  },
  headers() {
    // Of two rules setting one header, the last wins.
    return Promise.resolve([
      { source: "/:path*", headers: securityHeaders },
      { source: "/bookings/:code/pay", headers: paymentPageHeaders },
    ]);
  },
  rewrites() {
    return Promise.resolve(
      apiProxyTarget === ""
        ? []
        : [{ source: "/v1/:path*", destination: `${apiProxyTarget}/v1/:path*` }],
    );
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
