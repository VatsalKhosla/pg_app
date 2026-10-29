import type { Metadata } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { ConsentPrompt } from "@/components/account/consent-prompt";
import { DataRequests } from "@/components/account/data-requests";
import { MarketingConsent } from "@/components/account/marketing-consent";
import { ProfileForm } from "@/components/account/profile-form";
import { errorText, profileText } from "@/components/auth/sign-in-text";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { publicEnv } from "@/config/env";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { ACCOUNT_PATH, OWNER_HOME_PATH, VISITS_PATH, STAFF_HOME_PATH } from "@/lib/auth/routes";
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
    <div className="mx-auto w-full max-w-2xl space-y-10 px-4 py-10 sm:py-16">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">
          {t("phone")}: <span className="font-medium text-foreground">{me.phone}</span>
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

      <section aria-labelledby="details-title" className="space-y-4">
        <h2 id="details-title" className="text-lg font-semibold">
          {t("details")}
        </h2>
        <ProfileForm text={await profileText()} initial={me} />
      </section>

      <section aria-labelledby="data-title" className="space-y-4">
        <div className="space-y-1">
          <h2 id="data-title" className="text-lg font-semibold">
            {t("dataTitle")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("dataIntro")}</p>
        </div>
        <DataRequests
          initial={requests.items}
          apiOrigin={publicEnv.apiUrl.origin}
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

      <section aria-labelledby="messages-title" className="space-y-4">
        <h2 id="messages-title" className="text-lg font-semibold">
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

      <div className="flex flex-wrap items-center gap-4 border-t pt-6">
        <SignOutButton
          label={t("signOut")}
          busyLabel={t("signingOut")}
          failedLabel={t("signOutFailed")}
        />
        {isStaff(me) ? (
          <Link
            href={STAFF_HOME_PATH}
            className="text-sm font-medium text-primary underline underline-offset-4"
          >
            {t("staffTools")}
          </Link>
        ) : null}
        {isStaff(me) ? null : (
          <Link
            href={VISITS_PATH}
            className="text-sm font-medium text-primary underline underline-offset-4"
          >
            {t("visits")}
          </Link>
        )}
        {isOwner(me) ? (
          <Link
            href={OWNER_HOME_PATH}
            className="text-sm font-medium text-primary underline underline-offset-4"
          >
            {t("ownerArea")}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
