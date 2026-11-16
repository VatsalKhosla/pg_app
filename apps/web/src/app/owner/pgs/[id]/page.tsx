import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { BarRows } from "@/components/charts/bar-rows";
import { RingMeter } from "@/components/charts/ring-meter";
import { DocumentUpload } from "@/components/owner/document-upload";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { OWNER_PGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";

const sectionClass =
  "space-y-5 rounded-[2rem] border border-border/70 bg-card p-5 shadow-md sm:p-7";
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
  const count = (value: number) => format.number(value);
  const funnel = [
    { key: "views", label: t("views"), value: insights.views, shown: count(insights.views) },
    {
      key: "visits",
      label: t("visits"),
      value: insights.visitRequests,
      shown: count(insights.visitRequests),
    },
    {
      key: "bookings",
      label: t("bookings"),
      value: insights.bookings,
      shown: count(insights.bookings),
    },
  ];
  const share = insights.takenBps === null ? 0 : Math.round(insights.takenBps / 100);
  // One scale for every room type's rents, so their bars compare across rooms too.
  const rentScale = Math.max(
    0,
    ...insights.rooms.flatMap((room) => [room.rentPaise, room.localityMedianPaise ?? 0]),
  );
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

      <section aria-labelledby="numbers-title" className={sectionClass}>
        <h2 id="numbers-title" className="text-title-3 font-semibold tracking-tight">
          {t("insightsTitle", { days: DAYS })}
        </h2>
        <div className="grid items-center gap-8 md:grid-cols-[minmax(0,14rem)_1fr]">
          <div className="space-y-3">
            <RingMeter value={insights.bedsTaken} total={insights.beds}>
              <p className="text-title-1 leading-none font-semibold tabular-nums">
                {insights.takenBps === null ? t("noValue") : t("percent", { value: share })}
              </p>
              <p className="mt-1 text-sm font-medium text-muted-foreground">{t("takenWord")}</p>
            </RingMeter>
            <p className="text-center text-sm font-semibold tabular-nums">
              {t("bedsToday", { taken: insights.bedsTaken, beds: insights.beds })}
            </p>
          </div>
          <div className="space-y-4">
            <BarRows label={t("funnel")} rows={funnel} />
            <p className="text-sm text-muted-foreground">
              {t("conversion")}:{" "}
              <span className="font-semibold text-foreground tabular-nums">
                {insights.conversionBps === null
                  ? t("noValue")
                  : t("percent", { value: percent(insights.conversionBps) })}
              </span>
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="rents-title" className={sectionClass}>
        <div className="space-y-1">
          <h2 id="rents-title" className="text-title-3 font-semibold tracking-tight">
            {t("rents")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("rentsLead")}</p>
        </div>
        <ul className="grid gap-6 lg:grid-cols-2">
          {insights.rooms.map((room) => (
            <li key={room.roomType} className="space-y-3 rounded-2xl bg-surface/60 p-4">
              <p className="font-semibold text-foreground">{room.roomType}</p>
              <BarRows
                label={t("rentsOf", { room: room.roomType })}
                max={rentScale}
                rows={[
                  {
                    key: "yours",
                    label: t("yourRent"),
                    value: room.rentPaise,
                    shown: formatINR(room.rentPaise),
                  },
                  ...(room.localityMedianPaise === null
                    ? []
                    : [
                        {
                          key: "locality",
                          label: `${t("median")} (${t("comparables", { count: room.comparables })})`,
                          value: room.localityMedianPaise,
                          shown: formatINR(room.localityMedianPaise),
                          muted: true,
                        },
                      ]),
                ]}
              />
              {room.localityMedianPaise === null ? (
                <p className="text-sm text-muted-foreground">{t("noMedian")}</p>
              ) : null}
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
