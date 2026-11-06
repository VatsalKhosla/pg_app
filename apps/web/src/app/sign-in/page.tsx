import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { SignInFlow } from "@/components/auth/sign-in-flow";
import { signInText } from "@/components/auth/sign-in-text";
import { ArchWatermark } from "@/components/brand/editorial-art";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
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
    <div className="mx-auto w-full max-w-lg px-gutter py-10 sm:py-16">
      <Card
        variant="raised"
        className="relative space-y-6 overflow-hidden rounded-3xl border-saffron-border/80 bg-card p-6 sm:p-8"
      >
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-1.5"
          style={{
            backgroundImage:
              "linear-gradient(90deg, var(--primary) 0%, var(--sage) 35%, var(--saffron) 70%, var(--coral) 100%)",
          }}
        />
        <ArchWatermark tone="coral" className="absolute -right-6 -bottom-6 size-36 opacity-15" />
        <div className="relative space-y-2 pt-1">
          <div aria-hidden="true" className="flex items-center gap-1.5">
            <span className="h-1.5 w-8 rounded-full bg-primary" />
            <span className="h-1.5 w-5 rounded-full bg-coral" />
            <span className="h-1.5 w-4 rounded-full bg-saffron" />
          </div>
          <h1 className="text-title-1 font-bold tracking-tight text-foreground">{t("title")}</h1>
        </div>
        <Separator />
        <div className="relative">
          <SignInFlow
            text={await signInText()}
            next={next}
            mode="people"
            turnstile={siteKey === undefined ? undefined : { siteKey, nonce }}
          />
        </div>
      </Card>
    </div>
  );
}
