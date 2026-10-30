import type { Schemas } from "@pg-platform/api-client";
import { getTranslations } from "next-intl/server";

import { formatINR } from "@/lib/money";
import { bpsText } from "@/lib/pricing/editor";

type Market = Schemas["PricingMarket"];
type Room = Market["rooms"][number];

/**
 * What a PG's rents sit beside (ARCHITECTURE §8.6): each active room's listed rent and the
 * owner's limits, the locality's band for its sharing, and the middle of what the locality's
 * other published PGs list for it; and the caps on every dynamic price. All the API's numbers.
 */
export async function MarketPanel({ market }: { market: Market }) {
  const t = await getTranslations("Ops.pricing.market");

  const limits = (room: Room) => {
    const { ownerMinPaise: min, ownerMaxPaise: max } = room;
    if (min !== null && max !== null) {
      return t("between", { min: formatINR(min), max: formatINR(max) });
    }
    if (min !== null) return t("atLeast", { min: formatINR(min) });
    if (max !== null) return t("atMost", { max: formatINR(max) });
    return t("none");
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("intro", { locality: market.locality })}</p>
      {market.rooms.length === 0 ? (
        <p>{t("noRooms")}</p>
      ) : (
        <ul className="space-y-3">
          {market.rooms.map((room) => (
            <li key={room.roomCategory} className="space-y-2 rounded-lg border p-4">
              <h3 className="font-medium">{room.label}</h3>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">{t("listed")}</dt>
                <dd className="tabular-nums">{formatINR(room.baseRentPaise)}</dd>
                <dt className="text-muted-foreground">{t("owner")}</dt>
                <dd>{limits(room)}</dd>
                <dt className="text-muted-foreground">{t("band")}</dt>
                <dd>
                  {room.band === null
                    ? t("noBand")
                    : `${t("between", {
                        min: formatINR(room.band.minRentPaise),
                        max: formatINR(room.band.maxRentPaise),
                      })} (${t(`sources.${room.band.source}`)})`}
                </dd>
                <dt className="text-muted-foreground">{t("median")}</dt>
                <dd>
                  {room.medianRentPaise === null
                    ? t("noMedian")
                    : t("medianOf", {
                        median: formatINR(room.medianRentPaise),
                        count: room.comparables,
                      })}
                </dd>
              </dl>
            </li>
          ))}
        </ul>
      )}
      <p className="text-sm text-muted-foreground">
        {t("caps", {
          premium: bpsText(market.caps.maxPremiumBps),
          discount: bpsText(-market.caps.maxDiscountBps),
          step: formatINR(market.caps.roundingStepPaise),
        })}
      </p>
    </div>
  );
}
