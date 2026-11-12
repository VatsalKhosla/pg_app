import {
  ArrowRight,
  Building2,
  CalendarDays,
  KeyRound,
  type LucideIcon,
  Mail,
  ShieldCheck,
  UserRound,
  Wrench,
} from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { ConsentPrompt } from "@/components/account/consent-prompt";
import { DataRequests } from "@/components/account/data-requests";
import { MarketingConsent } from "@/components/account/marketing-consent";
import { ProfileForm } from "@/components/account/profile-form";
import { errorText, profileText } from "@/components/auth/sign-in-text";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { publicEnv } from "@/config/env";
import { trustPages } from "@/lib/trust/pages";
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

  const who = me.name ?? me.phone;
  const sections = [
    { id: "details", label: t("details"), Icon: UserRound },
    { id: "stays", label: t("staysTitle"), Icon: CalendarDays },
    { id: "messages", label: t("messagesTitle"), Icon: Mail },
    { id: "data", label: t("dataTitle"), Icon: ShieldCheck },
  ] as const;
  const tiles = [
    ...(isStaff(me)
      ? [{ href: STAFF_HOME_PATH as Route, label: t("staffTools"), Icon: Wrench }]
      : [
          { href: VISITS_PATH as Route, label: t("visits"), Icon: CalendarDays },
          { href: BOOKINGS_PATH as Route, label: t("bookings"), Icon: KeyRound },
        ]),
    ...(isOwner(me)
      ? [{ href: OWNER_HOME_PATH as Route, label: t("ownerArea"), Icon: Building2 }]
      : []),
  ];
  const sectionClass =
    "scroll-mt-40 space-y-5 rounded-[1.75rem] border border-border/70 bg-card p-6 shadow-md sm:p-8";
  const heading = (id: string, Icon: LucideIcon, title: string) => (
    <div className="flex items-center gap-3">
      <span
        aria-hidden="true"
        className="grid size-11 place-items-center rounded-2xl bg-primary-soft text-primary-soft-foreground"
      >
        <Icon className="size-5" />
      </span>
      <h2 id={`${id}-title`} className="text-title-2 font-medium">
        {title}
      </h2>
    </div>
  );

  return (
    <div className="mx-auto w-full max-w-4xl px-gutter pt-8 pb-section sm:pt-12">
      <header className="scope-night relative isolate overflow-hidden rounded-[2rem] p-7 sm:p-10">
        <div aria-hidden="true" className="sky-band absolute inset-0 -z-10" />
        <div className="flex flex-wrap items-center gap-5">
          <span
            aria-hidden="true"
            className="grid size-16 place-items-center rounded-full bg-sun font-display text-3xl text-sun-foreground shadow-lg"
          >
            {who.charAt(0).toUpperCase() || "?"}
          </span>
          <div className="min-w-0">
            <h1 className="text-display font-medium">{t("title")}</h1>
            <p className="mt-1 truncate text-night-foreground">{t("greeting", { who })}</p>
          </div>
        </div>
      </header>

      <nav
        aria-label={t("jumpTo")}
        className="glass sticky top-24 z-20 mt-6 flex gap-2 overflow-x-auto rounded-full p-1.5 shadow-md [scrollbar-width:none]"
      >
        {sections.map(({ id, label, Icon }) => (
          <a
            key={id}
            href={`#${id}`}
            className="inline-flex min-h-10 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium text-foreground outline-none hover:bg-primary-soft hover:text-primary-soft-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Icon aria-hidden="true" className="size-4" />
            {label}
          </a>
        ))}
      </nav>

      {!me.consentRequired ? null : (
        <div className="mt-6">
          <ConsentPrompt
            noticeVersion={notice.version}
            text={{
              body: t("consentBody"),
              read: t("consentRead"),
              agree: t("consentAgree"),
              failed: t("consentFailed"),
            }}
          />
        </div>
      )}

      <div className="mt-6 grid gap-6">
        <section id="details" aria-labelledby="details-title" className={sectionClass}>
          {heading("details", UserRound, t("details"))}
          <ProfileForm text={await profileText()} initial={me} />
        </section>

        <section id="stays" aria-labelledby="stays-title" className={sectionClass}>
          {heading("stays", CalendarDays, t("staysTitle"))}
          <p className="text-muted-foreground">{t("staysIntro")}</p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {tiles.map(({ href, label, Icon }) => (
              <li key={href}>
                <Link
                  href={href}
                  className="group flex items-center gap-4 rounded-2xl border border-border/70 bg-surface p-4 font-medium outline-none transition-colors hover:border-primary/40 hover:bg-primary-soft focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
                >
                  <span
                    aria-hidden="true"
                    className="grid size-11 place-items-center rounded-xl bg-linear-to-br from-primary to-[color-mix(in_oklch,var(--primary)_55%,var(--ember))] text-primary-foreground"
                  >
                    <Icon className="size-5" />
                  </span>
                  <span className="flex-1">{label}</span>
                  <ArrowRight
                    aria-hidden="true"
                    className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1 motion-reduce:transition-none"
                  />
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section id="messages" aria-labelledby="messages-title" className={sectionClass}>
          {heading("messages", Mail, t("messagesTitle"))}
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

        <section id="data" aria-labelledby="data-title" className={sectionClass}>
          {heading("data", ShieldCheck, t("dataTitle"))}
          <p className="text-muted-foreground">{t("dataIntro")}</p>
          <DataRequests
            allowExport={false}
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
          <p className="text-sm text-muted-foreground">
            <Link
              href={trustPages.contact}
              className="font-medium text-primary underline underline-offset-4"
            >
              {t("copyHint")}
            </Link>
          </p>
        </section>

        <div className="flex flex-wrap items-center gap-3 px-1">
          <SignOutButton
            label={t("signOut")}
            busyLabel={t("signingOut")}
            failedLabel={t("signOutFailed")}
          />
        </div>
      </div>
    </div>
  );
}
