import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BudgetExplorer, type BudgetExplorerText } from "@/components/home/budget-explorer";
import { type MapPin, mapPins } from "@/lib/search/client";

vi.mock("@/lib/search/client", () => ({ mapPins: vi.fn() }));

const text: BudgetExplorerText = {
  budget: "Your monthly budget",
  one: "{count} PG at or under {budget}.",
  other: "{count} PGs at or under {budget}.",
  none: "None at or under {budget}.",
  more: "There may be more.",
  cta: "See them on the map",
  monthly: "a month",
  caption: "Rough locations.",
  mapLabel: "A map of PGs",
};

function pin(id: string, minRentPaise: number): MapPin {
  return {
    id,
    slug: id,
    lat: 28.65 + minRentPaise / 1e9,
    lng: 77.2,
    minRentPaise,
    maxRentPaise: minRentPaise,
    genderPolicy: "coed",
    verified: true,
    bedsFree: "some",
  };
}

function answer(pins: MapPin[], truncated = false) {
  vi.mocked(mapPins).mockResolvedValue({ pins, truncated, month: "2027-07-01" });
}

function setBudget(paise: number) {
  fireEvent.change(screen.getByRole("slider", { name: "Your monthly budget" }), {
    target: { value: String(paise) },
  });
}

describe("the budget explorer", () => {
  beforeEach(() => {
    vi.mocked(mapPins).mockReset();
  });

  it("counts the real pins whose lowest rent is within the budget, and links to them", async () => {
    answer([pin("a", 800_000), pin("b", 1_000_000), pin("c", 1_500_000)]);
    render(<BudgetExplorer text={text}>fallback</BudgetExplorer>);

    await waitFor(() => {
      expect(screen.getByRole("slider", { name: "Your monthly budget" })).toBeTruthy();
    });
    setBudget(1_000_000);

    expect(screen.getByText("2 PGs at or under ₹10,000.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See them on the map" }).getAttribute("href")).toBe(
      "/search?budget_max_paise=1000000",
    );
    setBudget(800_000);
    expect(screen.getByText("1 PG at or under ₹8,000.")).toBeTruthy();
  });

  it("keeps what the server drew when there are no pins to show", async () => {
    answer([]);
    render(<BudgetExplorer text={text}>fallback</BudgetExplorer>);

    await waitFor(() => {
      expect(mapPins).toHaveBeenCalled();
    });
    expect(screen.getByText("fallback")).toBeTruthy();
    expect(screen.queryByRole("slider")).toBeNull();
  });

  it("doesn't claim a total when the map was cut short", async () => {
    answer([pin("a", 800_000), pin("b", 1_000_000)], true);
    render(<BudgetExplorer text={text}>fallback</BudgetExplorer>);

    await waitFor(() => {
      expect(screen.getByRole("slider", { name: "Your monthly budget" })).toBeTruthy();
    });
    setBudget(1_000_000);

    expect(screen.getByText(/2\+ PGs at or under ₹10,000\./u)).toBeTruthy();
    expect(screen.getByText(/There may be more\./u)).toBeTruthy();
  });
});
