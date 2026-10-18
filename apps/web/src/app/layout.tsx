import "./globals.css";

import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { connection } from "next/server";
import { getLocale, getTranslations } from "next-intl/server";

import { ErrorTextProvider } from "@/components/layout/error-text";
import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { brand, brandStyle } from "@/config/brand";
import { publicEnv } from "@/config/env";

// Self-hosted at build time by next/font: no request to Google from the browser, no layout shift.
const sans = Inter({ subsets: ["latin"], display: "swap", variable: "--font-sans-face" });

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const tBrand = await getTranslations("Brand");
  const t = await getTranslations("Metadata");

  return {
    metadataBase: publicEnv.siteUrl,
    title: { default: `${brand.name} · ${tBrand("tagline")}`, template: `%s · ${brand.name}` },
    description: t("description"),
    applicationName: brand.name,
    appleWebApp: { title: brand.name },
    // Keep iOS from turning rents and booking codes into phone links.
    formatDetection: { telephone: false },
    openGraph: { type: "website", siteName: brand.name, locale: locale.replace("-", "_") },
    // Staging must never show up in search results.
    robots: publicEnv.appEnv === "staging" ? { index: false, follow: false } : undefined,
  };
}

export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: brand.surfaces.light },
    { media: "(prefers-color-scheme: dark)", color: brand.surfaces.dark },
  ],
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Render every page per request: the Content Security Policy's nonce is new on each response
  // (src/proxy.ts), and Next.js can only put it on the scripts of a page rendered for that request.
  await connection();
  const locale = await getLocale();
  const t = await getTranslations("Layout");
  const tError = await getTranslations("Error");

  // Client components get their text translated on the server, as props or (for the error page,
  // which can't take props) through ErrorTextProvider, so the browser ships no message formatter.
  return (
    <html lang={locale} className={sans.variable} style={brandStyle}>
      <body className="flex min-h-dvh flex-col font-sans antialiased">
        <a
          href="#main"
          className="sr-only rounded-md bg-background px-4 py-2 font-medium shadow-lg ring-[3px] ring-ring/50 focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50"
        >
          {t("skipToContent")}
        </a>
        <SiteHeader />
        <main id="main" tabIndex={-1} className="flex flex-1 flex-col outline-none">
          <ErrorTextProvider
            text={{
              title: tError("title"),
              body: tError("body"),
              retry: tError("retry"),
              referenceLabel: tError("referenceLabel"),
            }}
          >
            {children}
          </ErrorTextProvider>
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
