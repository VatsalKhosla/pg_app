import type { Schemas } from "@pg-platform/api-client";
import { describe, expect, it } from "vitest";

import {
  breadcrumbJsonLd,
  faqJsonLd,
  itemListJsonLd,
  jsonLdText,
  listingJsonLd,
  rupeesText,
} from "@/lib/seo/json-ld";

type PublicListing = Schemas["PublicListing"];

function category(label: string, baseRentPaise: number): PublicListing["categories"][number] {
  return {
    id: `00000000-0000-7000-8000-${String(baseRentPaise).padStart(12, "0")}`,
    occupancy: "double",
    label,
    ac: false,
    attachedBath: false,
    balcony: false,
    baseRentPaise,
    securityDepositPaise: baseRentPaise,
    mandatoryCharges: [],
    monthlyChargesPaise: 0,
    oneTimeChargesPaise: 0,
  };
}

const listing = {
  id: "00000000-0000-7000-8000-000000000001",
  slug: "fictional-sample-pg-aster-kamla-nagar",
  name: "Fictional Sample PG Aster",
  description: "A fictional PG </script> for tests.",
  locality: { slug: "kamla-nagar", name: "Kamla Nagar" },
  displayLocation: { lat: 28.6871, lng: 77.2134 },
  genderPolicy: "girls",
  meals: "two",
  houseRules: [],
  verified: true,
  safety: null,
  licenceStatus: "not_applied",
  societyPermission: "unknown",
  campusesNearby: [],
  stationsNearby: [],
  ownerBusinessName: "Aster Stays",
  amenities: [{ slug: "wifi", name: "Wi-Fi" }],
  categories: [category("2 to a room", 1_250_000), category("3 to a room", 900_050)],
  media: [
    {
      id: "00000000-0000-7000-8000-000000000002",
      contentType: "image/jpeg",
      verifiedCapture: true,
      renditions: [
        {
          name: "gallery",
          contentType: "image/webp",
          url: "https://media.example.test/gallery.webp",
          width: 1200,
          height: 900,
        },
      ],
    },
  ],
} as unknown as PublicListing;

const URL_OF = "https://www.example.test/pg/fictional-sample-pg-aster-kamla-nagar";

describe("structured data", () => {
  it("keeps any text in it from closing its script", () => {
    expect(jsonLdText({ name: "</script><script>alert(1)</script>" })).not.toContain("<");
    expect(JSON.parse(jsonLdText({ name: "a <b>" }))).toEqual({ name: "a <b>" });
  });

  it("writes paise as rupees with paise, exactly", () => {
    expect(rupeesText(1_250_000)).toBe("12500.00");
    expect(rupeesText(900_050)).toBe("9000.50");
    expect(rupeesText(5)).toBe("0.05");
  });

  it("says what a PG offers, where it is roughly and nothing more", () => {
    const data = listingJsonLd(listing, URL_OF);

    expect(data).toMatchObject({
      "@type": "LodgingBusiness",
      name: "Fictional Sample PG Aster",
      url: URL_OF,
      image: ["https://media.example.test/gallery.webp"],
      address: { "@type": "PostalAddress", addressLocality: "Kamla Nagar", addressCountry: "IN" },
      geo: { latitude: 28.6871, longitude: 77.2134 },
      priceRange: "₹9,000.50–₹12,500",
      amenityFeature: [{ name: "Wi-Fi", value: true }],
    });
    expect(data.makesOffer).toMatchObject([
      { name: "2 to a room", priceSpecification: { price: "12500.00", priceCurrency: "INR" } },
      { name: "3 to a room", priceSpecification: { price: "9000.50", priceCurrency: "INR" } },
    ]);
    // The address stays with the owner until a visit or booking (CLAUDE.md rule 11).
    expect(JSON.stringify(data)).not.toMatch(/streetAddress|postalCode|telephone/u);
  });

  it("lists a landing page's PGs, its breadcrumbs and its questions", () => {
    const url = (path: string) => `https://www.example.test${path}`;
    const cards = [
      { slug: "pg-a", name: "PG A" },
      { slug: "pg-b", name: "PG B" },
    ] as unknown as Schemas["SearchCard"][];

    expect(itemListJsonLd("PGs near Hindu College", cards, url)).toMatchObject({
      "@type": "ItemList",
      numberOfItems: 2,
      itemListElement: [
        { position: 1, url: "https://www.example.test/pg/pg-a", name: "PG A" },
        { position: 2, url: "https://www.example.test/pg/pg-b", name: "PG B" },
      ],
    });
    expect(
      breadcrumbJsonLd([
        { name: "Home", url: url("/") },
        { name: "PGs near Hindu College", url: url("/pg-near/hindu-college") },
      ]).itemListElement,
    ).toEqual([
      { "@type": "ListItem", position: 1, name: "Home", item: "https://www.example.test/" },
      {
        "@type": "ListItem",
        position: 2,
        name: "PGs near Hindu College",
        item: "https://www.example.test/pg-near/hindu-college",
      },
    ]);
    expect(faqJsonLd([{ question: "Q?", answer: "A." }])).toMatchObject({
      "@type": "FAQPage",
      mainEntity: [{ "@type": "Question", name: "Q?", acceptedAnswer: { text: "A." } }],
    });
  });
});
