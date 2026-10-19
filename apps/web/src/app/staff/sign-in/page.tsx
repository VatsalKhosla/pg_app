import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { SignInFlow } from "@/components/auth/sign-in-flow";
import { signInText } from "@/components/auth/sign-in-text";
import { buttonVariants } from "@/components/ui/button";
import { brand } from "@/config/brand";
import { publicEnv } from "@/config/env";
import { safeNext, STAFF_HOME_PATH } from "@/lib/auth/routes";
import { getSessionForHeader, isStaff } from "@/lib/auth/session";

/** The codes the API's Google callback sends back here (ADR 0016). */
const GOOGLE_ERRORS = [
  "STAFF_ACCOUNT_NOT_ALLOWED",
  "STAFF_SIGN_IN_EXPIRED",
  "STAFF_SIGN_IN_CANCELLED",
  "SERVICE_UNAVAILABLE",
] as const;
type GoogleError = (typeof GOOGLE_ERRORS)[number];

function isGoogleError(value: unknown): value is GoogleError {
  return typeof value === "string" && (GOOGLE_ERRORS as readonly string[]).includes(value);
}

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Staff");
  return { title: t("signInMetaTitle"), robots: { index: false, follow: false } };
}

export default async function StaffSignInPage({ searchParams }: PageProps<"/staff/sign-in">) {
  const params = await searchParams;
  const next = safeNext(params.next, STAFF_HOME_PATH);
  const me = await getSessionForHeader();
  if (me !== null && isStaff(me)) redirect(next);
  const t = await getTranslations("Staff");
  const error = isGoogleError(params.error) ? t(`errors.${params.error}`) : undefined;
  const siteKey = publicEnv.turnstileSiteKey;
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <div className="mx-auto w-full max-w-md space-y-8 px-4 py-10 sm:py-16">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("signInTitle")}</h1>
        <p className="text-muted-foreground">{t("signInIntro", { brand: brand.name })}</p>
      </div>
      {error === undefined ? null : (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 p-3 text-sm text-destructive"
        >
          {error}
        </p>
      )}
      <div className="space-y-2">
        {/* A full navigation to the API, which sends the browser on to Google and back. */}
        <a
          href={`${publicEnv.apiUrl.origin}/v1/auth/staff/google`}
          className={buttonVariants({ size: "lg", className: "w-full" })}
        >
          {t("google")}
        </a>
        <p className="text-sm text-muted-foreground">{t("googleHint")}</p>
      </div>
      <div className="space-y-6 border-t pt-6">
        <p className="text-sm text-muted-foreground">{t("withoutGoogle")}</p>
        <SignInFlow
          text={await signInText()}
          next={next}
          mode="staff"
          turnstile={siteKey === undefined ? undefined : { siteKey, nonce }}
        />
      </div>
    </div>
  );
}
