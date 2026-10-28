import type { Schemas } from "@pg-platform/api-client";

import { formatINR } from "@/lib/money";

/**
 * Structured data for search engines (schema.org JSON-LD; step 3.6, ADR 0032). Public details
 * only, as the pages show them: the locality and the display point, never the address or the
 * exact point (CLAUDE.md rule 11). Amounts are the API's, written as rupees with paise.
 */

type PublicListing = Schemas["PublicListing"];
type SearchCard = Schemas["SearchCard"];
export type Thing = Record<string, unknown>;

const CONTEXT = "https://schema.org";
// Photos a search engine may show: the first few, at the gallery's size.
const MAX_IMAGES = 5;

/** The document as a <script> body: "<" escaped, so no text in it can close the script. */
export function jsonLdText(data: Thing | Thing[]): string {
  return JSON.stringify(data).replace(/</gu, "\\u003c");
}

/** Paise as schema.org writes a price: "12500.00" rupees, worked out without floating point. */
export function rupeesText(paise: number): string {
  const rest = paise % 100;
  return `${String((paise - rest) / 100)}.${String(rest).padStart(2, "0")}`;
}

function images(listing: PublicListing): string[] {
  return listing.media
    .filter((media) => media.contentType.startsWith("image/"))
    .flatMap((media) => {
      const found =
        media.renditions.find((rendition) => rendition.name === "gallery") ??
        media.renditions.find((rendition) => rendition.contentType.startsWith("image/"));
      return found === undefined ? [] : [found.url];
    })
    .slice(0, MAX_IMAGES);
}

/** A PG as a lodging business, with an offer for each room category's rent a month. */
export function listingJsonLd(listing: PublicListing, url: string): Thing {
  const rents = listing.categories.map((category) => category.baseRentPaise);
  const low = Math.min(...rents);
  const high = Math.max(...rents);
  return {
    "@context": CONTEXT,
    "@type": "LodgingBusiness",
    "@id": `${url}#pg`,
    name: listing.name,
    description: listing.description,
    url,
    image: images(listing),
    address: {
      "@type": "PostalAddress",
      addressLocality: listing.locality.name,
      addressCountry: "IN",
    },
    geo: {
      "@type": "GeoCoordinates",
      latitude: listing.displayLocation.lat,
      longitude: listing.displayLocation.lng,
    },
    ...(rents.length === 0
      ? {}
      : { priceRange: low === high ? formatINR(low) : `${formatINR(low)}–${formatINR(high)}` }),
    amenityFeature: listing.amenities.map((amenity) => ({
      "@type": "LocationFeatureSpecification",
      name: amenity.name,
      value: true,
    })),
    makesOffer: listing.categories.map((category) => ({
      "@type": "Offer",
      name: category.label,
      priceSpecification: {
        "@type": "UnitPriceSpecification",
        price: rupeesText(category.baseRentPaise),
        priceCurrency: "INR",
        // A bed, each month.
        referenceQuantity: { "@type": "QuantitativeValue", value: 1, unitCode: "MON" },
      },
      itemOffered: { "@type": "Accommodation", name: category.label },
    })),
  };
}

/** A landing page's PGs, in the order it lists them. */
export function itemListJsonLd(
  name: string,
  cards: readonly SearchCard[],
  url: (path: string) => string,
): Thing {
  return {
    "@context": CONTEXT,
    "@type": "ItemList",
    name,
    numberOfItems: cards.length,
    itemListElement: cards.map((card, index) => ({
      "@type": "ListItem",
      position: index + 1,
      url: url(`/pg/${card.slug}`),
      name: card.name,
    })),
  };
}

export function breadcrumbJsonLd(items: readonly { name: string; url: string }[]): Thing {
  return {
    "@context": CONTEXT,
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

export function faqJsonLd(questions: readonly { question: string; answer: string }[]): Thing {
  return {
    "@context": CONTEXT,
    "@type": "FAQPage",
    mainEntity: questions.map(({ question, answer }) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  };
}

/** The business behind the site, for the home page. */
export function organizationJsonLd({
  name,
  url,
  logo,
}: {
  name: string;
  url: string;
  logo: string;
}): Thing {
  return { "@context": CONTEXT, "@type": "Organization", name, url, logo };
}
