import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { DocumentUpload } from "@/components/owner/document-upload";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { OWNER_PGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;
const DAYS = 30;

/** Basis points as a percentage people read: 2500 is "25". */
function percent(bps: number): string {
  return String(bps / 100);
}

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.pg");
  return { title: t("metaTitle") };
}

/**
 * One of the owner's PGs (Phase 7, ADR 0063): its last month in numbers, its rents beside the
 * locality's, its documents with a way to add one, and the way to its beds and its pricing. The
 * numbers are the API's own counts; nothing is worked out here.
 */
export default async function OwnerPgPage({ params }: PageProps<"/owner/pgs/[id]">) {
  const { id } = await params;
  const path = `${OWNER_PGS_PATH}/${id}`;
  await requireOwner(path as Route);
  if (!UUID.test(id)) notFound();
  const api = await getServerApi();
  const where = { params: { path: { property_id: id } } };
  let insights, documents;
  try {
    [insights, documents] = await Promise.all([
      unwrap(
        api.GET("/v1/owner/properties/{property_id}/insights", {
          params: { path: { property_id: id }, query: { days: DAYS } },
        }),
      ),
      unwrap(api.GET("/v1/owner/properties/{property_id}/documents", where)),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [t, format] = await Promise.all([getTranslations("Owner.pg"), getFormatter()]);
  const day = (moment: string) => format.dateTime(new Date(moment), { dateStyle: "medium" });
  const numbers = [
    { term: t("views"), value: String(insights.views) },
    { term: t("visits"), value: String(insights.visitRequests) },
    { term: t("bookings"), value: String(insights.bookings) },
    {
      term: t("conversion"),
      value:
        insights.conversionBps === null
          ? t("noValue")
          : t("percent", { value: percent(insights.conversionBps) }),
    },
    {
      term: t("taken"),
      value: t("takenOf", { taken: insights.bedsTaken, beds: insights.beds }),
    },
  ];
  const kinds = (["licence", "society_permission"] as const).map((value) => ({
    value,
    label: t(`kind.${value}`),
  }));

  return (
    <>
      <div className="space-y-2">
        <Link
          href={OWNER_PGS_PATH}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("back")}
        </Link>
        <h1 className="font-display text-title-1 text-foreground">{insights.name}</h1>
      </div>

      <nav aria-label={t("links")} className="flex flex-wrap gap-3">
        <Link
          href={`${path}/calendar` as Route}
          className="inline-flex min-h-11 items-center rounded-full border border-border/80 bg-card px-5 text-sm font-medium text-foreground shadow-xs transition-colors hover:bg-surface"
        >
          {t("calendar")}
        </Link>
        <Link
          href={`${path}/pricing` as Route}
          className="inline-flex min-h-11 items-center rounded-full border border-border/80 bg-card px-5 text-sm font-medium text-foreground shadow-xs transition-colors hover:bg-surface"
        >
          {t("pricing")}
        </Link>
      </nav>

      <section aria-labelledby="numbers-title" className="space-y-3">
        <h2 id="numbers-title" className="font-display text-title-3 text-foreground">
          {t("insightsTitle", { days: DAYS })}
        </h2>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {numbers.map((number) => (
            <div
              key={number.term}
              className="rounded-2xl border border-border/80 bg-card p-4 shadow-xs"
            >
              <dt className="text-sm text-muted-foreground">{number.term}</dt>
              <dd className="mt-1 font-display text-2xl font-semibold text-foreground tabular-nums">
                {number.value}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="rents-title" className="space-y-3">
        <h2 id="rents-title" className="font-display text-title-3 text-foreground">
          {t("rents")}
        </h2>
        <ul className="divide-y divide-border/60 rounded-2xl border border-border/80 bg-card shadow-xs">
          {insights.rooms.map((room) => (
            <li key={room.roomType} className="space-y-1 p-4">
              <p className="font-semibold text-foreground">{room.roomType}</p>
              <p className="text-sm tabular-nums">
                {t("yourRent")}: {formatINR(room.rentPaise)}
              </p>
              <p className="text-sm text-muted-foreground tabular-nums">
                {room.localityMedianPaise === null
                  ? t("noMedian")
                  : `${t("median")}: ${formatINR(room.localityMedianPaise)} (${t("comparables", { count: room.comparables })})`}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="documents-title" className="space-y-3">
        <h2 id="documents-title" className="font-display text-title-3 text-foreground">
          {t("documentsTitle")}
        </h2>
        <p className="text-sm text-muted-foreground">{t("documentsIntro")}</p>
        {documents.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("documentsNone")}</p>
        ) : (
          <ul className="divide-y divide-border/60 rounded-2xl border border-border/80 bg-card shadow-xs">
            {documents.items.map((document) => (
              <li key={document.id} className="space-y-1 p-4">
                <p className="font-semibold text-foreground">{t(`kind.${document.kind}`)}</p>
                <p className="text-sm text-muted-foreground">
                  {t(`documentStatus.${document.status}`)} ·{" "}
                  {t("added", { date: day(document.addedAt) })}
                </p>
                {document.note === null ? null : (
                  <p className="text-sm">{t("note", { note: document.note })}</p>
                )}
                {document.files[0] === undefined ? null : (
                  <a
                    href={document.files[0].url}
                    className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
                  >
                    {t("view")}
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
        <DocumentUpload
          propertyId={id}
          kinds={kinds}
          text={{
            title: t("upload.title"),
            kind: t("upload.kind"),
            file: t("upload.file"),
            submit: t("upload.submit"),
            working: t("upload.working"),
            done: t("upload.done"),
            refused: t("upload.refused"),
            failed: t("upload.failed"),
            needFile: t("upload.needFile"),
          }}
        />
      </section>
    </>
  );
}
