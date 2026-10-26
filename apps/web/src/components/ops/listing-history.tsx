import "server-only";

import type { Schemas } from "@pg-platform/api-client";
import { getFormatter, getTranslations } from "next-intl/server";

import { formatINR } from "@/lib/money";

import { isListingStatus } from "./choices";

type Entry = Schemas["HistoryEntry"];

/** The audit log's actions (apps/api/src/app/modules/catalog/service), by their message. */
const ACTIONS = {
  "catalog.property_created": "created",
  "catalog.property_updated": "updated",
  "catalog.property_status_changed": "statusChanged",
  "catalog.amenities_set": "amenitiesSet",
  "catalog.media_set": "mediaSet",
  "catalog.room_category_added": "categoryAdded",
  "catalog.room_category_updated": "categoryUpdated",
  "catalog.room_added": "roomAdded",
  "catalog.bed_added": "bedAdded",
  "catalog.bed_status_changed": "bedStatusChanged",
  "catalog.verification_scheduled": "verificationScheduled",
  "catalog.verification_cancelled": "verificationCancelled",
  "catalog.verification_submitted": "verificationSubmitted",
  "catalog.verification_suspended": "verificationSuspended",
} as const;

/** The fields an update names (the API's own names), as the forms call them. */
const FIELDS = {
  name: "name",
  address_line: "address",
  location: "location",
  location_precision: "precision",
  gender_policy: "gender",
  meals: "meals",
  description: "description",
  house_rules: "houseRules",
  licence_status: "licence",
  licence_number: "licenceNumber",
  society_permission: "society",
  instant_confirm: "instantConfirm",
  label: "label",
  ac: "ac",
  attached_bath: "attachedBath",
  balcony: "balcony",
  base_rent: "baseRent",
  owner_min_rent: "ownerMin",
  owner_max_rent: "ownerMax",
  security_deposit: "deposit",
  mandatory_charges: "charges",
  status: "offered",
} as const;

function isResult(value: unknown): value is "passed" | "failed" {
  return value === "passed" || value === "failed";
}

function isKnown<T extends object>(map: T, key: unknown): key is keyof T {
  return typeof key === "string" && Object.hasOwn(map, key);
}

/** Everything done to a listing, its rooms and its beds, newest first. */
export async function ListingHistory({ entries }: { entries: Entry[] }) {
  const t = await getTranslations("Ops.history");
  const tStatus = await getTranslations("Ops.status");
  const tSummary = await getTranslations("Field.summary");
  const format = await getFormatter();

  function summary(entry: Entry): string | null {
    const { details } = entry;
    if (Array.isArray(details.fields)) {
      const names = details.fields.filter((field) => isKnown(FIELDS, field));
      const rent = details.base_rent_paise as { from?: unknown; to?: unknown } | undefined;
      const parts = [names.map((field) => t(`fields.${FIELDS[field]}`)).join(", ")];
      if (typeof rent?.from === "number" && typeof rent.to === "number") {
        parts.push(t("rent", { from: formatINR(rent.from), to: formatINR(rent.to) }));
      }
      return parts.filter((part) => part !== "").join(" · ") || null;
    }
    if (entry.action === "catalog.property_status_changed") {
      const { from, to, reason } = details;
      if (isListingStatus(from) && isListingStatus(to)) {
        const moved = t("moved", { from: tStatus(from), to: tStatus(to) });
        return typeof reason === "string" ? `${moved} (${reason})` : moved;
      }
    }
    if (entry.action === "catalog.verification_submitted" && isResult(details.result)) {
      return tSummary(`results.${details.result}`);
    }
    if (typeof details.reason === "string") return details.reason;
    if (entry.action === "catalog.bed_status_changed") {
      return details.to === "inactive" ? t("bedOut") : t("bedBack");
    }
    return null;
  }

  if (entries.length === 0) return <p className="text-sm text-muted-foreground">{t("empty")}</p>;
  return (
    <ol className="space-y-3">
      {entries.map((entry, index) => {
        const said = summary(entry);
        return (
          <li key={`${entry.occurredAt}-${String(index)}`} className="text-sm">
            <p>
              <span className="font-medium">
                {isKnown(ACTIONS, entry.action)
                  ? t(`actions.${ACTIONS[entry.action]}`)
                  : entry.action}
              </span>
              {said === null ? null : <span className="text-muted-foreground"> · {said}</span>}
            </p>
            <p className="text-xs text-muted-foreground">
              <time dateTime={entry.occurredAt}>
                {format.dateTime(new Date(entry.occurredAt), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </time>
              {" · "}
              {entry.actorType === "staff" ? t("staff") : t("system")}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
