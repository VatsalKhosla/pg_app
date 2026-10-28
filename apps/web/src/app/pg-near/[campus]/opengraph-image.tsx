import { ImageResponse } from "next/og";

import { OG_SIZE, OgCard } from "@/components/seo/og-card";
import { getCampus, getSearchPlaces } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { ogText } from "@/lib/seo/og-text";

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;
const t = ogText.landing;

export const alt = t("og.alt");
export const size = OG_SIZE;
export const contentType = "image/png";

/** A campus's landing page picture (step 3.6): how many PGs are near it, from what rent. */
export default async function Image({ params }: { params: Promise<{ campus: string }> }) {
  const { campus: slug } = await params;
  const campus = SLUG.test(slug) && slug.length <= 64 ? await getCampus(slug) : null;
  if (campus === null) {
    return new ImageResponse(<OgCard eyebrow="" title="" facts={[]} />, {
      ...OG_SIZE,
      status: 404,
    });
  }
  const place = (await getSearchPlaces()).items.find(
    (item) => item.kind === "campus" && item.slug === slug,
  );
  return new ImageResponse(
    <OgCard
      eyebrow={ogText.brand("tagline")}
      title={t("near.title", { campus: campus.name })}
      facts={
        place === undefined
          ? []
          : [
              t("og.count", { count: place.listings }),
              t("og.from", { min: formatINR(place.minRentPaise) }),
            ]
      }
    />,
    OG_SIZE,
  );
}
