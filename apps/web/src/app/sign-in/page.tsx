import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { SignInFlow } from "@/components/auth/sign-in-flow";
import { signInText } from "@/components/auth/sign-in-text";
import { publicEnv } from "@/config/env";
import { ACCOUNT_PATH, safeNext } from "@/lib/auth/routes";
import { getSessionForHeader } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("SignIn");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  const next = safeNext((await searchParams).next, ACCOUNT_PATH);
  // Signed in already: straight on. If the API can't say, the form shows what's wrong when used.
  if ((await getSessionForHeader()) !== null) redirect(next);
  const t = await getTranslations("SignIn");
  const siteKey = publicEnv.turnstileSiteKey;
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <div className="mx-auto w-full max-w-md px-4 py-10 sm:py-16">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
      <div className="mt-8">
        <SignInFlow
          text={await signInText()}
          next={next}
          mode="people"
          turnstile={siteKey === undefined ? undefined : { siteKey, nonce }}
        />
      </div>
    </div>
  );
}
