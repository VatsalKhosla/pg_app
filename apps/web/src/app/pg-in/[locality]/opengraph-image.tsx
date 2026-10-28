import { ImageResponse } from "next/og";

import { OG_SIZE, OgCard } from "@/components/seo/og-card";
import { getSearchPlaces, getSearchReference } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { ogText } from "@/lib/seo/og-text";

const t = ogText.landing;

export const alt = t("og.alt");
export const size = OG_SIZE;
export const contentType = "image/png";

/** A locality's landing page picture (step 3.6): how many PGs are in it, from what rent. */
export default async function Image({ params }: { params: Promise<{ locality: string }> }) {
  const { locality: slug } = await params;
  const locality = (await getSearchReference()).localities.find((each) => each.slug === slug);
  if (locality === undefined) {
    return new ImageResponse(<OgCard eyebrow="" title="" facts={[]} />, {
      ...OG_SIZE,
      status: 404,
    });
  }
  const place = (await getSearchPlaces()).items.find(
    (item) => item.kind === "locality" && item.slug === slug,
  );
  return new ImageResponse(
    <OgCard
      eyebrow={ogText.brand("tagline")}
      title={t("in.title", { locality: locality.name })}
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
