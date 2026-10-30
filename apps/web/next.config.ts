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

// The container image (apps/web/Dockerfile) builds Next.js's standalone server, traced from the
// repository's root so the workspace's API client comes along. Vercel builds need neither.
const standalone = process.env.NEXT_OUTPUT === "standalone";

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
  },
  headers() {
    return Promise.resolve([{ source: "/:path*", headers: securityHeaders }]);
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
