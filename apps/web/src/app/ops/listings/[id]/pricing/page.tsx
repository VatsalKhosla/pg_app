import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { ActivateDraft, DiscardDraft, StartDraft } from "@/components/ops/pricing/draft-actions";
import { MarketPanel } from "@/components/ops/pricing/market-panel";
import { type ChartRoom, PriceCharts } from "@/components/ops/pricing/price-chart";
import { PreviewPanel } from "@/components/ops/pricing/preview-panel";
import { RulesEditor } from "@/components/ops/pricing/rules-editor";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { requireOps } from "@/lib/auth/session";
import { addDays, DEFAULT_STAY, dayText, PREVIEW_DAYS } from "@/lib/pricing/editor";
import { indiaDate } from "@/lib/visits/times";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;
const DATE = /^\d{4}-\d{2}-\d{2}$/u;
const STAYS = [1, 3, 6, 9, 11, 12, 18, 24, 36] as const;

type Version = Schemas["RuleSetSummaryInfo"];

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.pricing");
  return { title: t("metaTitle") };
}

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

/** The version to show: the one asked for, else the draft, the one in force or the latest. */
function chosen(versions: readonly Version[], asked: string | undefined): Version | undefined {
  return (
    versions.find((version) => version.id === asked) ??
    versions.find((version) => version.status === "draft") ??
    versions.find((version) => version.status === "active") ??
    versions[0]
  );
}

async function load(id: string) {
  const api = await getServerApi();
  const path = { params: { path: { property_id: id } } };
  try {
    return await Promise.all([
      unwrap(api.GET("/v1/ops/properties/{property_id}", path)),
      unwrap(api.GET("/v1/ops/properties/{property_id}/rule-sets", path)),
      unwrap(api.GET("/v1/ops/properties/{property_id}/market", path)),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

async function loadVersion(id: string, query: { from?: string; stay: number }) {
  const api = await getServerApi();
  const path = { rule_set_id: id };
  return Promise.all([
    unwrap(api.GET("/v1/ops/rule-sets/{rule_set_id}", { params: { path } })),
    unwrap(
      api.GET("/v1/ops/rule-sets/{rule_set_id}/calendar", {
        params: { path, query: { stay: query.stay, ...(query.from ? { from: query.from } : {}) } },
      }),
    ),
  ]);
}

/**
 * A PG's pricing editor (ARCHITECTURE §8.6; step 4.6, ADR 0041): its versions, the shown one's
 * rules (a draft's to change), what stops a draft going into force, the band and market beside
 * its rents, a preview of any move-in and stay, and a 12-week chart, then activation once
 * confirmed. Owners get the same in Phase 7.
 */
export default async function PricingPage({
  params,
  searchParams,
}: PageProps<"/ops/listings/[id]/pricing">) {
  const { id } = await params;
  const pricingPath = `/ops/listings/${id}/pricing`;
  await requireOps(pricingPath as Route);
  if (!UUID.test(id)) notFound();
  const query = await searchParams;
  const today = indiaDate(new Date());
  const askedStay = Number(one(query.stay));
  const stay = (STAYS as readonly number[]).includes(askedStay) ? askedStay : DEFAULT_STAY;
  const askedFrom = one(query.from);
  const from = askedFrom !== undefined && DATE.test(askedFrom) ? askedFrom : undefined;

  const [listing, versions, market] = await load(id);
  const shown = chosen(versions.items, one(query.version));
  const [set, calendar] =
    shown === undefined
      ? [null, null]
      : await loadVersion(shown.id, { stay, ...(from ? { from } : {}) });
  const t = await getTranslations("Ops.pricing");
  const active = versions.items.find((version) => version.status === "active");
  const draft = versions.items.find((version) => version.status === "draft");
  const rooms = listing.categories.map((category) => ({ id: category.id, label: category.label }));
  const activeRooms = market.rooms.map((room) => ({ id: room.roomCategory, label: room.label }));
  const stays = STAYS.map((months) => ({
    value: months,
    label: t("preview.months", { count: months }),
  }));
  const bands = new Map(market.rooms.map((room) => [room.roomCategory, room.band]));
  const charted: ChartRoom[] =
    calendar?.rooms.map((room) => {
      const band = bands.get(room.roomCategory) ?? null;
      return {
        id: room.roomCategory,
        label: room.label,
        baseRentPaise: room.baseRentPaise,
        bedsFree: room.bedsFree,
        weeks: room.weeks,
        band:
          band === null
            ? null
            : { minRentPaise: band.minRentPaise, maxRentPaise: band.maxRentPaise },
      };
    }) ?? [];

  const versionLine = (version: Version) =>
    [
      t(`versions.status.${version.status}`),
      version.status === "active" && version.activatedAt !== null
        ? t("versions.since", { date: dayText(indiaDate(new Date(version.activatedAt))) })
        : null,
      version.status === "archived" && version.archivedAt !== null
        ? t("versions.retired", { date: dayText(indiaDate(new Date(version.archivedAt))) })
        : null,
      t("versions.rules", { count: version.rules }),
    ]
      .filter(Boolean)
      .join(" · ");

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
        <p className="text-muted-foreground">{[listing.name, listing.locality.name].join(" · ")}</p>
        <p className="max-w-prose text-sm text-muted-foreground">{t("intro")}</p>
      </div>

      <section aria-labelledby="versions-title" className="space-y-4">
        <h2 id="versions-title" className="border-b pb-2 text-lg font-semibold">
          {t("versions.title")}
        </h2>
        {versions.items.length === 0 ? <p>{t("versions.none")}</p> : null}
        {versions.items.length === 0 ? null : (
          <ul aria-label={t("versions.label")} className="space-y-2">
            {versions.items.map((version) => (
              <li key={version.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                {version.id === shown?.id ? (
                  <span aria-current="true" className="font-semibold">
                    {t("versions.version", { version: version.version })}
                  </span>
                ) : (
                  <Link
                    href={`${pricingPath}?version=${version.id}` as Route}
                    className="inline-flex min-h-6 items-center font-medium text-primary underline underline-offset-4"
                  >
                    {t("versions.version", { version: version.version })}
                  </Link>
                )}
                <span className="text-sm text-muted-foreground">
                  {versionLine(version)}
                  {version.id === shown?.id ? ` · ${t("versions.shown")}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        {draft === undefined ? <StartDraft propertyId={id} pricingPath={pricingPath} /> : null}
        {draft !== undefined && draft.id !== shown?.id ? (
          <Link
            href={`${pricingPath}?version=${draft.id}` as Route}
            className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
          >
            {t("versions.viewDraft")}
          </Link>
        ) : null}
      </section>

      <div className="grid gap-10 lg:grid-cols-[3fr_2fr]">
        {set === null ? null : (
          <section aria-labelledby="rules-title" className="min-w-0 space-y-4">
            <h2 id="rules-title" className="border-b pb-2 text-lg font-semibold">
              {`${t("rules.title")}: ${t("versions.version", { version: set.version })}`}
            </h2>
            <RulesEditor
              ruleSetId={set.id}
              rules={set.rules}
              rooms={rooms}
              editable={set.status === "draft"}
            />
            {set.status === "draft" ? (
              <div className="space-y-4">
                <div
                  role={set.problems.length > 0 ? "alert" : undefined}
                  className="space-y-2 rounded-lg border p-4"
                >
                  <h3 className="font-medium">{t("problems.title")}</h3>
                  {set.problems.length === 0 ? (
                    <p className="text-sm">{t("problems.none")}</p>
                  ) : (
                    <ul className="list-disc space-y-1 pl-5 text-sm">
                      {set.problems.map((problem) => (
                        <li key={problem}>{problem}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="flex flex-wrap items-start gap-3">
                  <ActivateDraft
                    ruleSetId={set.id}
                    version={set.version}
                    current={active?.version ?? null}
                    blocked={set.problems.length > 0}
                    pricingPath={pricingPath}
                  />
                  <DiscardDraft
                    ruleSetId={set.id}
                    version={set.version}
                    pricingPath={pricingPath}
                  />
                </div>
              </div>
            ) : null}
          </section>
        )}
        <section aria-labelledby="market-title" className="min-w-0 space-y-4">
          <h2 id="market-title" className="border-b pb-2 text-lg font-semibold">
            {t("market.title")}
          </h2>
          <MarketPanel market={market} />
        </section>
      </div>

      {set === null ? null : (
        <section aria-labelledby="preview-title" className="space-y-4">
          <h2 id="preview-title" className="border-b pb-2 text-lg font-semibold">
            {t("preview.title")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("preview.intro")}</p>
          <PreviewPanel
            ruleSetId={set.id}
            revision={JSON.stringify(set.rules)}
            rooms={activeRooms}
            stays={stays}
            defaultStay={DEFAULT_STAY}
            today={today}
          />
        </section>
      )}

      {set === null ? null : (
        <section aria-labelledby="chart-title" className="space-y-4">
          <h2 id="chart-title" className="border-b pb-2 text-lg font-semibold">
            {t("chart.title")}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t("chart.intro", { stay: t("preview.months", { count: calendar.stayMonths }) })}
          </p>
          <form
            method="get"
            aria-label={t("chart.filters")}
            className="flex flex-wrap items-end gap-4"
          >
            <input type="hidden" name="version" value={set.id} />
            <Field id="chart-stay" label={t("chart.stay")}>
              {(control) => (
                <Select {...control} name="stay" defaultValue={String(calendar.stayMonths)}>
                  {stays.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field id="chart-from" label={t("chart.from")}>
              {(control) => (
                <Input
                  {...control}
                  type="date"
                  name="from"
                  min={today}
                  max={addDays(today, PREVIEW_DAYS)}
                  defaultValue={from ?? today}
                />
              )}
            </Field>
            <Button type="submit" variant="outline" className="h-11">
              {t("chart.show")}
            </Button>
          </form>
          {charted.every((room) => room.weeks.length === 0) && from !== undefined ? (
            <p>{t("chart.noWeeks")}</p>
          ) : (
            <PriceCharts rooms={charted} />
          )}
        </section>
      )}
    </div>
  );
}
