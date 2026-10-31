import type { Metadata, Route } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { DisputeResolve } from "@/components/ops/dispute-resolve";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { OPS_DISPUTES_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { dayText } from "@/lib/format/days";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.disputes");
  return { title: t("metaTitle") };
}

/**
 * One student's report that their room isn't as shown (step 5.7, ADR 0051): what they said, their
 * photos (behind links signed for five minutes), whom to call, the booking, and settling it.
 */
export default async function OpsDisputePage({ params }: PageProps<"/ops/disputes/[id]">) {
  const { id } = await params;
  await requireOps(`${OPS_DISPUTES_PATH}/${id}` as Route);
  if (!UUID.test(id)) notFound();
  const api = await getServerApi();
  let dispute;
  try {
    dispute = await unwrap(
      api.GET("/v1/ops/disputes/{dispute_id}", { params: { path: { dispute_id: id } } }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [t, format] = await Promise.all([getTranslations("Ops.disputes"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const { booking, student } = dispute;

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <Link
          href={OPS_DISPUTES_PATH}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("back")}
        </Link>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          {t("item", { code: booking.code, pg: booking.property.name })}
        </h1>
        <p className="text-muted-foreground">
          {t(`status.${dispute.status}`)} · {t(`reasons.${dispute.reason}`)} ·{" "}
          {t("openedOn", { when: when(dispute.openedAt) })}
        </p>
      </div>

      <section aria-labelledby="student" className="space-y-1">
        <h2 id="student" className="text-lg font-semibold">
          {t("student")}
        </h2>
        <p>{student.name ?? t("noName")}</p>
        <p>
          <a href={`tel:${student.phone}`} className="underline underline-offset-4">
            {student.phone}
          </a>
        </p>
      </section>

      <section aria-labelledby="said" className="space-y-2">
        <h2 id="said" className="text-lg font-semibold">
          {t("said")}
        </h2>
        <p className="leading-7 whitespace-pre-line">{dispute.description}</p>
      </section>

      <section aria-labelledby="photos" className="space-y-2">
        <h2 id="photos" className="text-lg font-semibold">
          {t("photos")}
        </h2>
        {dispute.photos.length === 0 ? (
          <p className="text-muted-foreground">{t("noPhotos")}</p>
        ) : (
          <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {dispute.photos.map((photo, index) => {
              const thumb = photo.sizes.find((size) => size.name === "card") ?? photo.sizes[0];
              const full = photo.sizes.find((size) => size.name === "full") ?? thumb;
              return (
                <li key={photo.id}>
                  {thumb === undefined || full === undefined ? (
                    <p className="text-sm text-muted-foreground">{t("photoMissing")}</p>
                  ) : (
                    <a
                      href={full.url}
                      target="_blank"
                      rel="noreferrer"
                      className="block overflow-hidden rounded-lg border outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    >
                      <span className="relative block aspect-[4/3] bg-muted">
                        <Image
                          src={thumb.url}
                          alt={t("photo", { number: index + 1 })}
                          fill
                          unoptimized
                          sizes="(min-width: 640px) 33vw, 50vw"
                          className="object-cover"
                        />
                      </span>
                    </a>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section aria-labelledby="booking" className="space-y-2">
        <h2 id="booking" className="text-lg font-semibold">
          {t("booking")}
        </h2>
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-muted-foreground">{t("bed")}</dt>
            <dd>{`${booking.roomType} · ${booking.room} · ${booking.bed}`}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">{t("moveIn")}</dt>
            <dd>{dayText(booking.moveIn)}</dd>
          </div>
          {booking.checkedInAt === null ? null : (
            <div>
              <dt className="text-sm text-muted-foreground">{t("movedIn")}</dt>
              <dd>{when(booking.checkedInAt)}</dd>
            </div>
          )}
          {booking.checkWindowEndsAt === null ? null : (
            <div>
              <dt className="text-sm text-muted-foreground">{t("windowEnds")}</dt>
              <dd>{when(booking.checkWindowEndsAt)}</dd>
            </div>
          )}
        </dl>
      </section>

      {dispute.status === "open" ? (
        <DisputeResolve id={dispute.id} code={booking.code} />
      ) : (
        <section aria-labelledby="settled" className="space-y-1">
          <h2 id="settled" className="text-lg font-semibold">
            {t("settled")}
          </h2>
          <p>
            {t(`status.${dispute.status}`)}
            {dispute.resolvedAt === null
              ? null
              : ` · ${t("settledOn", { when: when(dispute.resolvedAt) })}`}
          </p>
          {dispute.notes === null ? null : (
            <p className="leading-7 whitespace-pre-line">{dispute.notes}</p>
          )}
        </section>
      )}
    </div>
  );
}
