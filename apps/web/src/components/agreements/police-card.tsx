import { FileText, Printer, ShieldCheck } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { buttonVariants } from "@/components/ui/button-variants";
import type {
  OpsPoliceVerification,
  OwnerPoliceVerification,
  StudentPoliceVerification,
} from "@/lib/agreements/client";
import { GENDERS, ID_TYPES, OCCUPATIONS } from "@/lib/agreements/police-form";

import { DocumentCard } from "./document-card";
import { PoliceDetailsForm } from "./police-details-form";
import { PoliceSubmission } from "./police-submission";
import { TenantDetailsList } from "./tenant-details";

// The API's error codes these forms can meet (ARCHITECTURE §15, ADR 0070).
const ERROR_CODES = [
  "INVALID_TRANSITION",
  "POLICE_DETAILS_INVALID",
  "ACKNOWLEDGEMENT_INVALID",
  "RATE_LIMITED",
  "VALIDATION_ERROR",
] as const;

type Props =
  | { viewer: "student"; verification: StudentPoliceVerification; printHref?: undefined }
  | { viewer: "owner"; verification: OwnerPoliceVerification; printHref: Route }
  | { viewer: "ops"; verification: OpsPoliceVerification; printHref?: undefined };

/**
 * A tenant's police verification (ADR 0070), as the student, the owner or ops see it: where it is,
 * the details the student gave, and what each may do next: the student gives or corrects them;
 * the owner prints them, uploads the portal's acknowledgement and marks it verified; ops read.
 */
export async function PoliceCard(props: Props) {
  const { viewer, verification } = props;
  const [t, format] = await Promise.all([getTranslations("PoliceVerification"), getFormatter()]);
  const when = (moment: string) => format.dateTime(new Date(moment), { dateStyle: "medium" });
  const errors = {
    generic: t("errors.generic"),
    ...Object.fromEntries(ERROR_CODES.map((code) => [code, t(`errors.${code}`)])),
  };
  const steps = [
    {
      key: "details",
      at: verification.detailsSubmittedAt,
      note: null,
    },
    {
      key: "submitted",
      at: verification.submittedToPoliceAt,
      note:
        verification.policeReference === null
          ? null
          : t("reference", { reference: verification.policeReference }),
    },
    { key: "verified", at: verification.verifiedAt, note: null },
  ] as const;
  const files = "acknowledgement" in verification ? verification.acknowledgement : [];

  return (
    <DocumentCard
      id="police"
      icon={ShieldCheck}
      tone="green"
      title={t("title")}
      status={t(`status.${verification.status}`)}
      done={verification.status === "verified"}
    >
      <p className="leading-relaxed text-foreground">
        {t(`next.${viewer}.${verification.status}`)}
      </p>
      <ol className="grid gap-3 sm:grid-cols-3">
        {steps.map((step, index) => (
          <li
            key={step.key}
            className="space-y-1 rounded-2xl border border-border/80 bg-surface/50 p-4 text-sm"
          >
            <p className="font-semibold text-foreground">
              {t("stepNumber", { number: index + 1 })} {t(`steps.${step.key}`)}
            </p>
            <p className="text-muted-foreground">
              {step.at === null ? t("notYet") : t("on", { date: when(step.at) })}
            </p>
            {step.note === null ? null : <p className="text-muted-foreground">{step.note}</p>}
          </li>
        ))}
      </ol>
      {verification.erased ? (
        <p className="rounded-xl border border-border bg-surface/60 p-4 text-sm text-foreground">
          {t("erased")}
        </p>
      ) : null}
      {viewer === "student" && verification.canEdit ? (
        <PoliceDetailsForm
          code={verification.booking}
          details={verification.details}
          text={{
            title: t(verification.details === null ? "form.title" : "form.titleAgain"),
            intro: t("form.intro"),
            fullName: t("form.fullName"),
            parentName: t("form.parentName"),
            dateOfBirth: t("form.dateOfBirth"),
            gender: t("form.gender"),
            genders: Object.fromEntries(
              GENDERS.map((value) => [value, t(`form.genders.${value}`)]),
            ) as Record<(typeof GENDERS)[number], string>,
            phone: t("form.phone"),
            address: t("form.address"),
            line: t("form.line"),
            city: t("form.city"),
            district: t("form.district"),
            state: t("form.state"),
            pinCode: t("form.pinCode"),
            policeStation: t("form.policeStation"),
            occupation: t("form.occupation"),
            occupations: Object.fromEntries(
              OCCUPATIONS.map((value) => [value, t(`form.occupations.${value}`)]),
            ) as Record<(typeof OCCUPATIONS)[number], string>,
            institution: t("form.institution"),
            idType: t("form.idType"),
            idTypes: Object.fromEntries(
              ID_TYPES.map((value) => [value, t(`form.idTypes.${value}`)]),
            ) as Record<(typeof ID_TYPES)[number], string>,
            idLast4: t("form.idLast4"),
            idLast4Hint: t("form.idLast4Hint"),
            references: t("form.references"),
            referencesHint: t("form.referencesHint"),
            referenceName: t("form.referenceName"),
            referencePhone: t("form.referencePhone"),
            referenceRelation: t("form.referenceRelation"),
            addReference: t("form.addReference"),
            removeReference: t("form.removeReference"),
            consent: t("form.consent"),
            save: t(verification.details === null ? "form.save" : "form.update"),
            saving: t("form.saving"),
            messages: {
              required: t("form.messages.required"),
              aadhaar: t("form.messages.aadhaar"),
              phone: t("form.messages.phone"),
              pin: t("form.messages.pin"),
              last4: t("form.messages.last4"),
              aadhaarLast4: t("form.messages.aadhaarLast4"),
              consent: t("form.messages.consent"),
            },
            errors,
          }}
        />
      ) : verification.details === null ? null : (
        <div className="space-y-3">
          <h3 className="font-semibold text-foreground">
            {t(viewer === "student" ? "givenTitle" : "detailsTitle")}
          </h3>
          <TenantDetailsList details={verification.details} />
        </div>
      )}
      {files.length === 0 ? null : (
        <ul className="flex flex-wrap gap-3" data-print-hidden>
          {files.map((file) => (
            <li key={file.url}>
              <a
                href={file.url}
                className={buttonVariants({ variant: "outline", size: "sm" })}
                rel="noopener"
              >
                <FileText aria-hidden />
                {t("openAcknowledgement")}
              </a>
            </li>
          ))}
        </ul>
      )}
      {props.viewer === "owner" ? (
        <>
          {props.verification.details === null ? null : (
            <Link
              href={props.printHref}
              className={buttonVariants({ variant: "outline", size: "sm" })}
              data-print-hidden
            >
              <Printer aria-hidden />
              {t("owner.printLink")}
            </Link>
          )}
          {props.verification.canMarkSubmitted || props.verification.canMarkVerified ? (
            <PoliceSubmission
              code={props.verification.booking}
              canMarkSubmitted={props.verification.canMarkSubmitted}
              canMarkVerified={props.verification.canMarkVerified}
              text={{
                title: t("owner.upload.title"),
                intro: t("owner.upload.intro"),
                file: t("owner.upload.file"),
                fileHint: t("owner.upload.fileHint"),
                reference: t("owner.upload.reference"),
                submit: t("owner.upload.submit"),
                submitting: t("owner.upload.submitting"),
                uploading: t("owner.upload.uploading"),
                needFile: t("owner.upload.needFile"),
                refused: t("owner.upload.refused", { reason: "{reason}" }),
                tooSlow: t("owner.upload.tooSlow"),
                verify: t("owner.upload.verify"),
                verifyHint: t("owner.upload.verifyHint"),
                verifying: t("owner.upload.verifying"),
                errors,
              }}
            />
          ) : null}
        </>
      ) : null}
    </DocumentCard>
  );
}
