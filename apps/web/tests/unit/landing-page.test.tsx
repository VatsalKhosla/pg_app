import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { NextIntlClientProvider } from "next-intl";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { LandingPage } from "@/components/landing/landing-page";
import type { SearchCard } from "@/lib/search/client";

import messages from "../../messages/en-IN.json";
import { WCAG_22_AA } from "../wcag";

vi.mock("next/link", () => ({
  default: ({ href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props} />,
}));

vi.mock("@/components/seo/json-ld", () => ({
  JsonLd: () => null,
}));

const sampleCard: SearchCard = {
  id: "00000000-0000-7000-8000-000000000001",
  slug: "fictional-sample-pg-aster-kamla-nagar",
  name: "Fictional Sample PG Aster",
  locality: { slug: "kamla-nagar", name: "Kamla Nagar" },
  displayLocation: { lat: 28.6871, lng: 77.2134 },
  distanceM: 650,
  nearestStation: { slug: "vishwavidyalaya", name: "Vishwavidyalaya", distanceM: 480 },
  minRentPaise: 900_000,
  maxRentPaise: 1_250_000,
  genderPolicy: "girls",
  meals: "two",
  verified: true,
  licensed: true,
  cover: null,
  bedsFree: "many",
};

describe("LandingPage", () => {
  it("renders breadcrumbs, PG cards, nearby places and FAQs and meets WCAG 2.2 AA", async () => {
    const { container } = render(
      <NextIntlClientProvider locale="en-IN" messages={messages}>
        <main>
          <LandingPage
            path="/pg-near/hindu-college"
            text={{
              title: "PGs near Hindu College",
              intro:
                "3 verified PGs within 3 km of Hindu College, from ₹9,000 to ₹12,500 a month per bed.",
              none: "No verified PG within 3 km of Hindu College yet.",
              noneHint: "We list a PG only once our field agent has visited it.",
              map: "See them on the map",
              mapAll: "See all 3 on the map",
              list: "The PGs",
              nearby: "Localities nearby",
              breadcrumb: "Breadcrumb",
              home: "Home",
              search: "Find a PG",
              faq: "Questions students and parents ask",
            }}
            cards={[sampleCard]}
            mapHref="/search?campus=hindu-college"
            nearby={[{ href: "/pg-in/kamla-nagar", label: "Kamla Nagar: 3 PGs" }]}
            faqs={[
              {
                question: "How many PGs are there near Hindu College?",
                answer: "3 PGs are listed, each one visited and checked by our field agent.",
              },
            ]}
          />
        </main>
      </NextIntlClientProvider>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "PGs near Hindu College" })).toBeDefined();
    expect(screen.getByRole("region", { name: "The PGs" }).querySelectorAll("li")).toHaveLength(1);
    expect(
      screen
        .getByRole("region", { name: "Localities nearby" })
        .querySelector('a[href="/pg-in/kamla-nagar"]'),
    ).not.toBeNull();
    expect(
      screen.getByRole("heading", {
        level: 3,
        name: "How many PGs are there near Hindu College?",
      }),
    ).toBeDefined();

    const results = await axe.run(container, { runOnly: { type: "tag", values: WCAG_22_AA } });
    expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
});
