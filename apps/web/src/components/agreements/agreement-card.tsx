import { FileSignature, Printer } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { MarkdownText } from "@/components/content/markdown-text";
import { buttonVariants } from "@/components/ui/button-variants";
import type { OpsRentAgreement, RentAgreement, Side } from "@/lib/agreements/client";
import { ACCOUNT_PATH } from "@/lib/auth/routes";

import { DocumentCard } from "./document-card";
import { SignAgreement } from "./sign-agreement";

type Viewer = Side | "ops";

/** Ops' view carries every signature's evidence. */
function isOps(agreement: RentAgreement | OpsRentAgreement): agreement is OpsRentAgreement {
  return "bookingEndedAt" in agreement;
}

// The API's error codes signing can meet (ARCHITECTURE §15, ADR 0070).
const ERROR_CODES = [
  "SIGNING_CODE_INVALID",
  "SIGNING_CODE_EXPIRED",
  "SIGNING_CODE_LOCKED",
  "SIGNING_CODE_TOO_SOON",
  "AGREEMENT_TEXT_CHANGED",
  "AGREEMENT_NOT_READY",
  "INVALID_TRANSITION",
  "RATE_LIMITED",
  "SERVICE_UNAVAILABLE",
] as const;

/**
 * A booking's rent agreement (ADR 0070), as the student, the owner or ops see it: its status, who
 * has signed and when, the whole text (marked DRAFT until a lawyer has reviewed it), the way to
 * sign for whoever may, and a page to print it from.
 */
export async function AgreementCard({
  agreement,
  viewer,
  printHref,
}: {
  agreement: RentAgreement | OpsRentAgreement;
  viewer: Viewer;
  printHref?: Route;
}) {
  const [t, format] = await Promise.all([getTranslations("Agreements"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const signatures = new Map(agreement.signatures.map((each) => [each.signer, each]));
  const canSign = "canSign" in agreement && agreement.canSign;
  const done = agreement.status === "signed";

  return (
    <DocumentCard
      id="agreement"
      icon={FileSignature}
      title={t("title")}
      status={t(`status.${agreement.status}`)}
      done={done}
    >
      <p className="leading-relaxed text-foreground">{t(`next.${viewer}.${agreement.status}`)}</p>
      {agreement.draft ? (
        <p className="rounded-xl bg-warning-soft p-4 text-sm font-medium text-warning-soft-foreground">
          {t("draft")}
        </p>
      ) : null}
      {agreement.missing.length === 0 ? null : (
        <p className="rounded-xl border border-border bg-surface/60 p-4 text-sm text-foreground">
          {viewer === "student" ? (
            <>
              {t("missing.student")}{" "}
              <Link
                href={ACCOUNT_PATH}
                className="font-semibold text-primary underline underline-offset-4"
              >
                {t("addName")}
              </Link>
            </>
          ) : (
            t(`missing.${viewer}`)
          )}
        </p>
      )}
      <dl className="grid gap-3 sm:grid-cols-2">
        {(["student", "owner"] as const).map((side) => {
          const signature = signatures.get(side);
          return (
            <div
              key={side}
              className="space-y-1 rounded-2xl border border-border/80 bg-surface/50 p-4"
            >
              <dt className="text-sm text-muted-foreground">{t(`parties.${side}`)}</dt>
              <dd className="text-sm font-medium text-foreground">
                {signature === undefined
                  ? t("notSigned")
                  : t("signed", { name: signature.name, when: when(signature.signedAt) })}
              </dd>
            </div>
          );
        })}
      </dl>
      {isOps(agreement) && agreement.signatures.length > 0 ? (
        <Evidence agreement={agreement} />
      ) : null}
      <details
        open={canSign}
        className="group rounded-2xl border border-border/80 bg-background p-5"
      >
        <summary className="cursor-pointer text-sm font-semibold text-primary underline-offset-4 group-open:mb-4 hover:underline">
          {t("readFull")}
        </summary>
        <MarkdownText
          text={agreement.text}
          depth={2}
          className="space-y-4 text-sm text-foreground"
        />
        <p className="mt-5 text-xs break-all text-muted-foreground">
          {t("fingerprint", { version: agreement.templateVersion, sha: agreement.textSha256 })}
        </p>
      </details>
      {canSign && viewer !== "ops" ? (
        <SignAgreement
          side={viewer}
          code={agreement.booking}
          textSha256={agreement.textSha256}
          text={{
            title: t("sign.title"),
            intro: t("sign.intro"),
            getCode: t("sign.getCode"),
            sending: t("sign.sending"),
            sent: t("sign.sent"),
            resend: t("sign.resend"),
            developmentCode: t("sign.developmentCode", { code: "{code}" }),
            code: t("sign.code"),
            needCode: t("sign.needCode"),
            fullName: t("sign.fullName"),
            fullNameHint: t("sign.fullNameHint"),
            needName: t("sign.needName"),
            agree: t("sign.agree"),
            signing: t("sign.signing"),
            errors: {
              generic: t("sign.errors.generic"),
              ...Object.fromEntries(ERROR_CODES.map((code) => [code, t(`sign.errors.${code}`)])),
            },
          }}
        />
      ) : null}
      {printHref === undefined ? null : (
        <Link
          href={printHref}
          className={buttonVariants({ variant: "outline", size: "sm" })}
          data-print-hidden
        >
          <Printer aria-hidden />
          {t("printLink")}
        </Link>
      )}
    </DocumentCard>
  );
}

async function Evidence({ agreement }: { agreement: OpsRentAgreement }) {
  const [t, format] = await Promise.all([getTranslations("Agreements.evidence"), getFormatter()]);
  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-foreground">{t("title")}</h3>
      <ul className="space-y-3">
        {agreement.signatures.map((signature) => (
          <li
            key={signature.signer}
            className="space-y-1 rounded-2xl border border-border/80 bg-surface/50 p-4 text-sm"
          >
            <p className="font-medium text-foreground">
              {t("who", {
                side: signature.signer,
                name: signature.name,
                when: format.dateTime(new Date(signature.signedAt), {
                  dateStyle: "medium",
                  timeStyle: "medium",
                }),
              })}
            </p>
            <p className="text-muted-foreground">{t("ip", { ip: signature.ipAddress })}</p>
            <p className="break-all text-muted-foreground">
              {t("userAgent", { agent: signature.userAgent ?? "—" })}
            </p>
            <p className="font-mono text-xs break-all text-muted-foreground">
              {t("sha", { sha: signature.textSha256, version: signature.templateVersion })}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
