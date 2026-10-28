import { ImageResponse } from "next/og";

import { OG_SIZE, OgCard } from "@/components/seo/og-card";
import { getPublicListing } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { ogText } from "@/lib/seo/og-text";

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;
const t = ogText.pg;

export const alt = t("ogAlt");
export const size = OG_SIZE;
export const contentType = "image/png";

/** A PG's picture for social sites (step 3.6): its name, where it is, its lowest rent. */
export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const listing = SLUG.test(slug) && slug.length <= 80 ? await getPublicListing(slug) : null;
  if (listing === null) {
    return new ImageResponse(<OgCard eyebrow="" title="" facts={[]} />, {
      ...OG_SIZE,
      status: 404,
    });
  }
  const rents = listing.categories.map((category) => category.baseRentPaise);
  return new ImageResponse(
    <OgCard
      eyebrow={`${listing.locality.name} · ${t(`genderShort.${listing.genderPolicy}`)}`}
      title={listing.name}
      facts={[
        ...(rents.length === 0 ? [] : [t("ogFrom", { min: formatINR(Math.min(...rents)) })]),
        ...(listing.verified ? [t("verified")] : []),
      ]}
    />,
    OG_SIZE,
  );
}
