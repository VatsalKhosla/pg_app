import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/**
 * The owner area (ADR 0025): owners, signed in by phone, see their business as we keep it and
 * accept the owner agreement. Each page checks for an owner (src/lib/auth/session.ts); the proxy
 * has already sent people without a session to sign in. Pages translate on the server and pass
 * plain strings to the one form, so there's no message provider here (ADR 0011).
 */
export default function OwnerLayout({ children }: LayoutProps<"/owner">) {
  return <div className="mx-auto w-full max-w-2xl space-y-10 px-4 py-10 sm:py-16">{children}</div>;
}
