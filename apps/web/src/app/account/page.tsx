import type { Metadata } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { ConsentPrompt } from "@/components/account/consent-prompt";
import { DataRequests } from "@/components/account/data-requests";
import { MarketingConsent } from "@/components/account/marketing-consent";
import { ProfileForm } from "@/components/account/profile-form";
import { errorText, profileText } from "@/components/auth/sign-in-text";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { publicEnv } from "@/config/env";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import {
  ACCOUNT_PATH,
  BOOKINGS_PATH,
  OWNER_HOME_PATH,
  STAFF_HOME_PATH,
  VISITS_PATH,
} from "@/lib/auth/routes";
import { isOwner, isStaff, requireSession } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Account");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function AccountPage() {
  const me = await requireSession(ACCOUNT_PATH);
  const api = await getServerApi();
  const [requests, notice, consents] = await Promise.all([
    unwrap(api.GET("/v1/me/data-requests", { params: { query: { limit: 20 } } })),
    unwrap(api.GET("/v1/privacy-notice")),
    unwrap(api.GET("/v1/me/consents")),
  ]);
  const marketing = consents.consents.some(
    (consent) => consent.purpose === "marketing" && consent.withdrawnAt === null,
  );
  const t = await getTranslations("Account");
  // next-intl's formatter, so times show in India's time zone (src/i18n/config.ts), not the
  // server's.
  const format = await getFormatter();
  const formatDate = Object.fromEntries(
    requests.items.flatMap((item) =>
      item.expiresAt === null
        ? []
        : [
            [
              item.expiresAt,
              format.dateTime(new Date(item.expiresAt), {
                dateStyle: "medium",
                timeStyle: "short",
              }),
            ],
          ],
    ),
  );

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-gutter py-10 sm:py-16">
      <div className="space-y-2">
        <h1 className="text-title-1 font-semibold tracking-tight text-foreground">{t("title")}</h1>
        <p className="text-body text-muted-foreground">
          {t("phone")}: <span className="font-mono font-semibold text-foreground">{me.phone}</span>
        </p>
      </div>

      {!me.consentRequired ? null : (
        <ConsentPrompt
          noticeVersion={notice.version}
          text={{
            body: t("consentBody"),
            read: t("consentRead"),
            agree: t("consentAgree"),
            failed: t("consentFailed"),
          }}
        />
      )}

      <Card asChild className="space-y-5 rounded-2xl border-border/80 bg-card p-6">
        <section aria-labelledby="details-title">
          <h2 id="details-title" className="text-title-3 font-semibold tracking-tight">
            {t("details")}
          </h2>
          <Separator />
          <ProfileForm text={await profileText()} initial={me} />
        </section>
      </Card>

      <Card asChild className="space-y-5 rounded-2xl border-border/80 bg-card p-6">
        <section aria-labelledby="data-title">
          <div className="space-y-1">
            <h2 id="data-title" className="text-title-3 font-semibold tracking-tight">
              {t("dataTitle")}
            </h2>
            <p className="text-body-sm text-muted-foreground">{t("dataIntro")}</p>
          </div>
          <Separator />
          <DataRequests
            initial={requests.items}
            apiOrigin={publicEnv.browserApiOrigin}
            formatDate={formatDate}
            text={{
              exportButton: t("exportButton"),
              deletionButton: t("deletionButton"),
              deletionConfirm: t("deletionConfirm"),
              status: {
                exportReceived: t("status.exportReceived"),
                exportReady: t.raw("status.exportReady") as string,
                exportExpired: t("status.exportExpired"),
                deletionReceived: t("status.deletionReceived"),
                deletionCompleted: t("status.deletionCompleted"),
                deletionRejected: t.raw("status.deletionRejected") as string,
              },
              download: t("download"),
              errors: await errorText(),
            }}
          />
        </section>
      </Card>

      <Card asChild className="space-y-4 rounded-2xl border-border/80 bg-card p-6">
        <section aria-labelledby="messages-title">
          <h2 id="messages-title" className="text-title-3 font-semibold tracking-tight">
            {t("messagesTitle")}
          </h2>
          <MarketingConsent
            initial={marketing}
            noticeVersion={notice.version}
            text={{
              label: t("marketing"),
              saved: t("marketingSaved"),
              failed: t("marketingFailed"),
            }}
          />
        </section>
      </Card>

      <div className="flex flex-wrap items-center gap-3 border-t border-border/80 pt-6">
        <SignOutButton
          label={t("signOut")}
          busyLabel={t("signingOut")}
          failedLabel={t("signOutFailed")}
        />
        {isStaff(me) ? (
          <Link
            href={STAFF_HOME_PATH}
            className={buttonVariants({ variant: "ghost", size: "sm", shape: "pill" })}
          >
            {t("staffTools")}
          </Link>
        ) : null}
        {isStaff(me) ? null : (
          <Link
            href={VISITS_PATH}
            className={buttonVariants({ variant: "ghost", size: "sm", shape: "pill" })}
          >
            {t("visits")}
          </Link>
        )}
        {isStaff(me) ? null : (
          <Link
            href={BOOKINGS_PATH}
            className={buttonVariants({ variant: "ghost", size: "sm", shape: "pill" })}
          >
            {t("bookings")}
          </Link>
        )}
        {isOwner(me) ? (
          <Link
            href={OWNER_HOME_PATH}
            className={buttonVariants({ variant: "ghost", size: "sm", shape: "pill" })}
          >
            {t("ownerArea")}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
