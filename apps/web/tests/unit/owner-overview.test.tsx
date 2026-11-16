import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { BedDouble } from "lucide-react";
import type { Route } from "next";
import { describe, expect, it } from "vitest";

import { PeriodBars } from "@/components/charts/period-bars";
import { RingMeter } from "@/components/charts/ring-meter";
import { BedsByPg, NeedsYouCard, StatTile } from "@/components/owner/overview";

import { WCAG_22_AA } from "../wcag";

const CIRCUMFERENCE = 2 * Math.PI * 50;

function arcLength(container: HTMLElement): number | null {
  const arc = container.querySelector(".ring-meter-arc");
  if (arc === null) return null;
  return Number((arc.getAttribute("stroke-dasharray") ?? "").split(" ")[0]);
}

describe("RingMeter", () => {
  it("fills the share of the ring that is taken, and leaves the words to the text", () => {
    const { container } = render(
      <RingMeter value={3} total={4}>
        <p>75%</p>
      </RingMeter>,
    );

    expect(arcLength(container)).toBeCloseTo(CIRCUMFERENCE * 0.75, 1);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByText("75%")).toBeDefined();
  });

  it("draws no arc for nothing taken, and a closed one for everything", () => {
    const empty = render(
      <RingMeter value={0} total={10}>
        0%
      </RingMeter>,
    );
    expect(arcLength(empty.container)).toBeNull();

    const full = render(
      <RingMeter value={10} total={10}>
        100%
      </RingMeter>,
    );
    expect(arcLength(full.container)).toBeCloseTo(CIRCUMFERENCE, 1);
    expect(full.container.querySelector(".ring-meter-arc")?.getAttribute("stroke-linecap")).toBe(
      "butt",
    );
  });

  it("never draws past the whole, or with nothing to divide by", () => {
    const over = render(
      <RingMeter value={12} total={10}>
        !
      </RingMeter>,
    );
    expect(arcLength(over.container)).toBeCloseTo(CIRCUMFERENCE, 1);
    const none = render(
      <RingMeter value={0} total={0}>
        -
      </RingMeter>,
    );
    expect(arcLength(none.container)).toBeNull();
  });
});

describe("the owner's overview", () => {
  const pgs = [
    {
      id: "a",
      href: "/owner/pgs/a" as Route,
      name: "Fictional House",
      place: "Satya Niketan · Live",
      beds: 20,
      taken: 15,
      words: "15 of 20 taken",
    },
    {
      id: "b",
      href: "/owner/pgs/b" as Route,
      name: "Fictional Annexe",
      place: "Kamla Nagar · Paused",
      beds: 4,
      taken: 0,
      words: "0 of 4 taken",
    },
  ];

  it("gives each PG a bar as full as it is, with its numbers in words", () => {
    const { container } = render(<BedsByPg label="Beds at each PG" pgs={pgs} />);

    const fills = [...container.querySelectorAll<HTMLElement>(".share-bar-fill")];
    expect(fills.map((fill) => fill.style.width)).toEqual(["75%"]);
    expect(screen.getByRole("link", { name: "Fictional House" }).getAttribute("href")).toBe(
      "/owner/pgs/a",
    );
    expect(screen.getByText("0 of 4 taken")).toBeDefined();
    expect(screen.getByRole("list", { name: "Beds at each PG" })).toBeDefined();
  });

  it("meets WCAG 2.2 AA: tiles, a card that needs the owner, the bars and a chart", async () => {
    const { container } = render(
      <main>
        <h1>Fictional Homes</h1>
        <StatTile
          label="Tenants we placed"
          value="3"
          note="2 living with you now"
          Icon={BedDouble}
          tone="primary"
        />
        <NeedsYouCard
          href="/owner/bookings"
          title="1 booking waits for your answer"
          detail="The first is due by Sat 16 Nov, 2:30 pm."
          Icon={BedDouble}
          urgent
        />
        <BedsByPg label="Beds at each PG" pgs={pgs} />
        <PeriodBars
          id="rent"
          level={3}
          title="Rent from tenants we placed, by month"
          total="₹20,000 this month"
          periods={["Oct 26", "Nov 26"]}
          values={[1_000_000, 2_000_000]}
          axis={(value) => String(value)}
          value={(value) => String(value)}
          tableLabel="See the numbers"
          periodLabel="Month"
        />
      </main>,
    );

    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });

    expect(results.violations.map((violation) => violation.id)).toEqual([]);
    expect(screen.getByRole("heading", { level: 3 }).textContent).toBe(
      "Rent from tenants we placed, by month",
    );
  });
});
