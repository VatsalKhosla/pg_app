import type { Metadata } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { AcceptAgreement } from "@/components/owner/accept-agreement";
import { MarkdownText } from "@/components/content/markdown-text";
import { NotSetUp } from "@/components/owner/not-set-up";
import { OWNER_AGREEMENT_PATH, OWNER_HOME_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { getAgreement } from "@/lib/owner/server";

/** The API's error codes accepting can meet (ARCHITECTURE §15); AGREEMENT_CHANGED reloads. */
const ERROR_CODES = [
  "UNAUTHENTICATED",
  "CSRF_TOKEN_INVALID",
  "NOT_FOUND",
  "RATE_LIMITED",
  "SERVICE_UNAVAILABLE",
  "API_UNREACHABLE",
  "API_TIMEOUT",
] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.agreement");
  return { title: t("metaTitle") };
}

/**
 * The current owner agreement, to read and accept (ADR 0025). Owners land here until they've
 * accepted the current version, the first time and after every new one.
 */
export default async function OwnerAgreementPage({ searchParams }: PageProps<"/owner/agreement">) {
  await requireOwner(OWNER_AGREEMENT_PATH);
  const agreement = await getAgreement();
  if (agreement === null) return <NotSetUp />;
  const t = await getTranslations("Owner.agreement");
  const errors = await getTranslations("Owner.errors");
  const format = await getFormatter();
  // Set by the form when the agreement changed while the owner read it.
  const changedWhileReading = (await searchParams).changed === "1";
  const notice = agreement.accepted
    ? null
    : changedWhileReading
      ? t("changedWhileReading")
      : agreement.acceptedVersion === null
        ? t("firstTime")
        : t("changedSince", { version: agreement.acceptedVersion });

  return (
    <>
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("version", { version: agreement.version })}</p>
      </div>

      {notice === null ? null : (
        <p className="rounded-lg border bg-accent/40 p-4 text-sm">{notice}</p>
      )}
      {/* A draft can't be in force: production refuses one (OWNER_AGREEMENT_VERSION). */}
      {agreement.version.startsWith("draft") ? (
        <p className="rounded-lg border border-destructive/40 p-4 text-sm">{t("draft")}</p>
      ) : null}

      <MarkdownText text={agreement.text} />

      <section aria-labelledby="accept-title" className="space-y-4 rounded-lg border p-4">
        <h2 id="accept-title" className="text-lg font-semibold">
          {t("acceptTitle")}
        </h2>
        {agreement.accepted ? (
          <div className="space-y-3">
            <p>
              {agreement.acceptedAt === null
                ? t("accepted")
                : t("acceptedOn", {
                    date: format.dateTime(new Date(agreement.acceptedAt), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }),
                  })}
            </p>
            <Link
              href={OWNER_HOME_PATH}
              className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
            >
              {t("back")}
            </Link>
          </div>
        ) : (
          // A new text is a new form: nothing carries over from the version before.
          <AcceptAgreement
            key={agreement.documentSha256}
            version={agreement.version}
            documentSha256={agreement.documentSha256}
            text={{
              agree: t("agree", { version: agreement.version }),
              required: t("required"),
              submit: t("submit"),
              submitting: t("submitting"),
              errors: {
                generic: errors("generic"),
                ...Object.fromEntries(ERROR_CODES.map((code) => [code, errors(code)])),
              },
            }}
          />
        )}
      </section>
    </>
  );
}
