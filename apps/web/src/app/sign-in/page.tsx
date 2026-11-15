import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { type GoogleStart, SignInFlow } from "@/components/auth/sign-in-flow";
import { signInText } from "@/components/auth/sign-in-text";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { publicEnv } from "@/config/env";
import { codeChannels, getSignInSetup } from "@/lib/auth/methods";
import { ACCOUNT_PATH, safeNext } from "@/lib/auth/routes";
import { getSessionForHeader } from "@/lib/auth/session";

/** The codes the API's Google callback sends back here (ADR 0068). */
const GOOGLE_ERRORS = [
  "GOOGLE_ACCOUNT_NOT_USABLE",
  "GOOGLE_SIGN_IN_EXPIRED",
  "GOOGLE_SIGN_IN_CANCELLED",
  "ACCOUNT_SUSPENDED",
  "PRIVACY_NOTICE_CHANGED",
  "SERVICE_UNAVAILABLE",
] as const;
type GoogleError = (typeof GOOGLE_ERRORS)[number];

function isGoogleError(value: unknown): value is GoogleError {
  return typeof value === "string" && (GOOGLE_ERRORS as readonly string[]).includes(value);
}

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("SignIn");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  const params = await searchParams;
  const next = safeNext(params.next, ACCOUNT_PATH);
  // Signed in already: straight on. If the API can't say, the form shows what's wrong when used.
  if ((await getSessionForHeader()) !== null) redirect(next);
  const [t, setup] = await Promise.all([getTranslations("SignIn"), getSignInSetup()]);
  const siteKey = publicEnv.turnstileSiteKey;
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const google: GoogleStart | undefined = setup.methods.google
    ? {
        // A full navigation to the API, which sends the browser on to Google and back.
        href: `${publicEnv.browserApiOrigin}/v1/auth/google`,
        noticeVersion: setup.noticeVersion,
      }
    : undefined;

  return (
    <div className="mx-auto w-full max-w-lg px-gutter py-10 sm:py-16">
      <Card
        variant="raised"
        className="relative space-y-6 overflow-hidden rounded-3xl border-marigold-border/80 bg-card p-6 sm:p-8"
      >
        <div className="space-y-2">
          <h1 className="text-title-1 font-medium text-foreground">{t("title")}</h1>
        </div>
        <Separator />
        <div className="relative">
          <SignInFlow
            text={await signInText()}
            next={next}
            mode="people"
            channels={codeChannels(setup.methods)}
            google={google}
            notice={isGoogleError(params.error) ? t(`google.errors.${params.error}`) : undefined}
            consentNeeded={params.error === "CONSENT_REQUIRED"}
            turnstile={siteKey === undefined ? undefined : { siteKey, nonce }}
          />
        </div>
      </Card>
    </div>
  );
}
