import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { GrievanceForms } from "@/components/ops/grievance-forms";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { OPS_GRIEVANCES_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";

const TICKET = /^GR-[0-9A-HJKMNP-TV-Z]{8}$/u;

export async function generateMetadata({
  params,
}: PageProps<"/ops/grievances/[ticket]">): Promise<Metadata> {
  const { ticket } = await params;
  const t = await getTranslations("Ops.grievances");
  return { title: `${t("metaTitle")} ${ticket}` };
}

/**
 * One grievance (step 3.8, ADR 0034): who complained and how to reach them, what happened, what
 * has been done, and the officer's next step.
 */
export default async function OpsGrievancePage({ params }: PageProps<"/ops/grievances/[ticket]">) {
  const { ticket } = await params;
  await requireOps(`${OPS_GRIEVANCES_PATH}/${ticket}` as Route);
  if (!TICKET.test(ticket)) notFound();
  const api = await getServerApi();
  let grievance;
  try {
    grievance = await unwrap(
      api.GET("/v1/ops/grievances/{ticket_number}", {
        params: { path: { ticket_number: ticket } },
      }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [t, tGrievances, format] = await Promise.all([
    getTranslations("Ops.grievances"),
    getTranslations("Grievances"),
    getFormatter(),
  ]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const { complainant } = grievance;
  const log = [
    t("receivedOn", { when: when(grievance.receivedAt) }),
    ...(grievance.acknowledgedAt === null
      ? []
      : [t("acknowledgedOn", { when: when(grievance.acknowledgedAt) })]),
    ...(grievance.reply === "" ? [] : [tGrievances("reply", { reply: grievance.reply })]),
    ...(grievance.resolvedAt === null
      ? []
      : [t("resolvedOn", { when: when(grievance.resolvedAt) })]),
    ...(grievance.resolution === ""
      ? []
      : [tGrievances("resolution", { resolution: grievance.resolution })]),
  ];

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="font-mono text-2xl font-bold tracking-tight sm:text-3xl">
          {grievance.ticketNumber}
        </h1>
        <p className="text-muted-foreground">
          {tGrievances(`status.${grievance.status}`)} ·{" "}
          {tGrievances(`categories.${grievance.category}`)}
          {grievance.late ? ` · ${t("late")}` : null}
        </p>
        <p className="text-sm">
          {grievance.status === "received"
            ? t("acknowledgeBy", { when: when(grievance.acknowledgeBy) })
            : grievance.status === "acknowledged"
              ? t("resolveBy", { when: when(grievance.resolveBy) })
              : null}
        </p>
      </div>
      <section aria-labelledby="complainant" className="space-y-1">
        <h2 id="complainant" className="text-lg font-semibold">
          {t("complainant")}
        </h2>
        <p>
          {complainant.name === "" ? t("noName") : complainant.name} ·{" "}
          {complainant.account === null ? t("signedOut") : t("signedIn")}
        </p>
        {complainant.phone === null ? null : (
          <p>{t("contactPhone", { phone: complainant.phone })}</p>
        )}
        {complainant.email === null ? null : (
          <p>{t("contactEmail", { email: complainant.email })}</p>
        )}
      </section>
      <section aria-labelledby="details" className="space-y-2">
        <h2 id="details" className="text-lg font-semibold">
          {t("detailsTitle")}
        </h2>
        {grievance.reference === "" ? null : (
          <p className="text-sm text-muted-foreground">
            {t("about", { reference: grievance.reference })}
          </p>
        )}
        <p className="leading-7 whitespace-pre-line">{grievance.details}</p>
      </section>
      <section aria-labelledby="log" className="space-y-2">
        <h2 id="log" className="text-lg font-semibold">
          {t("logTitle")}
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          {log.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>
      {grievance.nextStatuses.length === 0 ? null : (
        <GrievanceForms
          ticket={grievance.ticketNumber}
          next={grievance.nextStatuses}
          text={{
            replyTitle: t("replyTitle"),
            replyHint: t("replyHint"),
            acknowledge: t("acknowledge"),
            resolutionTitle: t("resolutionTitle"),
            resolutionHint: t("resolutionHint"),
            resolve: t("resolve"),
            saving: t("saving"),
            needText: t("needText"),
            errors: { generic: t("errors.generic") },
          }}
        />
      )}
    </div>
  );
}
