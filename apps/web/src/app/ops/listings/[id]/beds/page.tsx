import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { BlockForm } from "@/components/ops/beds/block-form";
import { EndBlock } from "@/components/ops/beds/end-block";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { requireOps } from "@/lib/auth/session";
import { addDays, dayText } from "@/lib/format/days";
import { indiaDate } from "@/lib/visits/times";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;
const DATE = /^\d{4}-\d{2}-\d{2}$/u;
const SPANS = [30, 60, 120, 365] as const;
const DEFAULT_SPAN = 120;

type Allocation = Schemas["AllocationInfo"];

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.beds");
  return { title: t("metaTitle") };
}

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

/**
 * A PG's beds over time (ARCHITECTURE §6; step 5.1, ADR 0044): each room type's beds free for
 * the days shown, what holds each bed then, a way to end a block, and a form to hold a bed for
 * an offline tenant or maintenance. Owners get the same in Phase 7.
 */
export default async function BedsPage({
  params,
  searchParams,
}: PageProps<"/ops/listings/[id]/beds">) {
  const { id } = await params;
  const bedsPath = `/ops/listings/${id}/beds`;
  await requireOps(bedsPath as Route);
  if (!UUID.test(id)) notFound();
  const query = await searchParams;
  const today = indiaDate(new Date());
  const asked = one(query.from);
  const from = asked !== undefined && DATE.test(asked) ? asked : today;
  const askedDays = Number(one(query.days));
  const days = (SPANS as readonly number[]).includes(askedDays) ? askedDays : DEFAULT_SPAN;
  const api = await getServerApi();
  let view: Schemas["InventoryView"];
  try {
    view = await unwrap(
      api.GET("/v1/ops/properties/{property_id}/inventory", {
        params: { path: { property_id: id }, query: { from, days } },
      }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const t = await getTranslations("Ops.beds");
  // The window's last day: the API's end is the first day after it.
  const lastDay = addDays(view.end, -1);
  const span = (allocation: Allocation) =>
    allocation.end === null
      ? t("openEnded", { from: dayText(allocation.start) })
      : t("span", { from: dayText(allocation.start), until: dayText(addDays(allocation.end, -1)) });
  const choices = view.categories.flatMap((category) =>
    category.beds
      .filter((bed) => bed.active)
      .map((bed) => ({
        id: bed.id,
        label: t("add.bedOption", { category: category.label, room: bed.room, bed: bed.label }),
      })),
  );

  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <Link
          href={`/ops/listings/${id}` as Route}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("back")}
        </Link>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{view.property.name}</p>
        <p className="max-w-prose text-sm text-muted-foreground">{t("intro")}</p>
      </div>

      <form method="get" aria-label={t("window")} className="flex flex-wrap items-end gap-4">
        <Field id="beds-from" label={t("from")}>
          {(control) => <Input {...control} type="date" name="from" defaultValue={from} />}
        </Field>
        <Field id="beds-days" label={t("days")}>
          {(control) => (
            <Select {...control} name="days" defaultValue={String(days)}>
              {SPANS.map((each) => (
                <option key={each} value={each}>
                  {t("daysOption", { count: each })}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Button type="submit" variant="outline" className="h-11">
          {t("show")}
        </Button>
      </form>

      {view.categories.every((category) => category.beds.length === 0) ? (
        <p>{t("noRooms")}</p>
      ) : (
        view.categories.map((category) => (
          <section
            key={category.id}
            aria-labelledby={`category-${category.id}`}
            className="space-y-3"
          >
            <div className="space-y-1 border-b pb-2">
              <h2 id={`category-${category.id}`} className="text-lg font-semibold">
                {category.label}
              </h2>
              <p className="text-sm text-muted-foreground">
                {t("free", {
                  free: category.freeBeds,
                  total: category.activeBeds,
                  start: dayText(view.start),
                  end: dayText(lastDay),
                })}
              </p>
            </div>
            <ul className="divide-y rounded-lg border">
              {category.beds.map((bed) => (
                <li key={bed.id} className="space-y-3 p-4">
                  <p className="font-medium">
                    {`${t("room")} ${bed.room} · ${t("bed")} ${bed.label}`}
                    {bed.active ? null : (
                      <span className="ms-2 text-sm font-normal text-muted-foreground">
                        {t("outOfUse")}
                      </span>
                    )}
                  </p>
                  {bed.allocations.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{`${t("heldBy")}: ${t("nothing")}`}</p>
                  ) : (
                    <ul className="space-y-3">
                      {bed.allocations.map((allocation) => (
                        <li key={allocation.id} className="space-y-2">
                          <p className="text-sm">
                            <span className="font-medium">{t(`kinds.${allocation.kind}`)}</span>
                            {` · ${span(allocation)}`}
                            {allocation.note === "" ? null : ` · ${allocation.note}`}
                          </p>
                          {allocation.kind === "booking" ? null : (
                            <EndBlock
                              blockId={allocation.id}
                              label={t("endTitle", {
                                kind: t(`kinds.${allocation.kind}`),
                                bed: bed.label,
                              })}
                              today={today}
                            />
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      {choices.length === 0 ? null : (
        <section aria-labelledby="hold-title" className="space-y-4">
          <h2 id="hold-title" className="border-b pb-2 text-lg font-semibold">
            {t("add.title")}
          </h2>
          <BlockForm beds={choices} today={today} />
        </section>
      )}
    </div>
  );
}
