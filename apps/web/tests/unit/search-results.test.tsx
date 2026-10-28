import { QueryClient, QueryClientProvider, useInfiniteQuery } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { NextIntlClientProvider } from "next-intl";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { Results } from "@/components/search/results";
import { ApiError } from "@/lib/api/errors";
import type { SearchCard, SearchPage } from "@/lib/search/client";

import messages from "../../messages/en-IN.json";
import { WCAG_22_AA } from "../wcag";

// As in the menu's test: a plain link stands in for next/link, which needs the app router.
vi.mock("next/link", () => ({
  default: ({ href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props} />,
}));

function card(id: string, name: string): SearchCard {
  return {
    id,
    slug: `fictional-sample-pg-${id}`,
    name,
    locality: { slug: "sample-locality", name: "Sample Locality" },
    displayLocation: { lat: 28.68, lng: 77.21 },
    distanceM: 850,
    nearestStation: { slug: "sample-station", name: "Sample Station", distanceM: 420 },
    minRentPaise: 800_000,
    maxRentPaise: 1_200_000,
    genderPolicy: "girls",
    meals: "two",
    verified: true,
    licensed: false,
    cover: null,
    bedsFree: "few",
  };
}

function page(items: SearchCard[], nextCursor: string | null = null): SearchPage {
  return { items, nextCursor, month: "2026-11" };
}

function Harness({
  load,
  problem = null,
  onClear = vi.fn(),
}: {
  load: (cursor: string | undefined) => Promise<SearchPage>;
  problem?: string | null;
  onClear?: () => void;
}) {
  const results = useInfiniteQuery({
    queryKey: ["search"],
    queryFn: ({ pageParam }) => load(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  return (
    <Results
      results={results}
      problem={problem}
      hoveredId={null}
      onHover={vi.fn()}
      onClear={onClear}
    />
  );
}

function show(props: React.ComponentProps<typeof Harness>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <NextIntlClientProvider locale="en-IN" messages={messages}>
      <QueryClientProvider client={client}>
        <Harness {...props} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

async function wcag(container: HTMLElement) {
  return (await axe.run(container, { runOnly: [...WCAG_22_AA] })).violations;
}

describe("search results", () => {
  it("shows that it's loading, then the PGs a page at a time", async () => {
    const load = vi.fn((cursor: string | undefined) =>
      Promise.resolve(
        cursor === undefined
          ? page([card("a", "Fictional Sample PG A")], "page-2")
          : page([card("b", "Fictional Sample PG B")]),
      ),
    );
    const { container } = show({ load });

    expect(screen.getByRole("status").textContent).toBe("Finding PGs…");
    const first = await screen.findByRole("link", { name: /Fictional Sample PG A/ });
    expect(first.getAttribute("href")).toBe("/pg/fictional-sample-pg-a");
    expect(screen.getByText("₹8,000 to ₹12,000 a month")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("1 PG and more");
    expect(await wcag(container)).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Show more PGs" }));

    await screen.findByRole("link", { name: /Fictional Sample PG B/ });
    expect(load).toHaveBeenLastCalledWith("page-2");
    expect(screen.getByRole("status").textContent).toBe("2 PGs ");
    expect(screen.queryByRole("button", { name: "Show more PGs" })).toBeNull();
  });

  it("says when nothing matches, and offers to clear the filters", async () => {
    const onClear = vi.fn();
    const { container } = show({ load: () => Promise.resolve(page([])), onClear });

    expect((await screen.findByText("No PG matches all of that yet.")).getAttribute("role")).toBe(
      "status",
    );
    expect(await wcag(container)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("says why the API can't answer a search", async () => {
    const detail = "the map area must be inside Delhi NCR";
    const invalid = new ApiError({
      message: detail,
      status: 422,
      code: "SEARCH_INVALID",
      problem: {
        type: "about:blank",
        title: "Invalid search",
        status: 422,
        code: "SEARCH_INVALID",
        detail,
      },
    });
    show({ load: () => Promise.reject(invalid) });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("That search doesn't work:");
    expect(alert.textContent).toContain(detail);
  });

  it("shows a problem the page already knew of without asking", () => {
    const load = vi.fn(() => Promise.resolve(page([])));
    show({ load, problem: "the radius must be from 200 m to 15000 m" });

    expect(screen.getByRole("alert").textContent).toContain("the radius must be");
  });

  it("offers to try again when search fails", async () => {
    const load = vi
      .fn<(cursor: string | undefined) => Promise<SearchPage>>()
      .mockRejectedValueOnce(new ApiError({ message: "down", status: 503, code: "UNAVAILABLE" }))
      .mockResolvedValue(page([card("a", "Fictional Sample PG A")]));
    const { container } = show({ load });

    expect((await screen.findByRole("alert")).textContent).toContain("Search didn't work");
    expect(await wcag(container)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await screen.findByRole("link", { name: /Fictional Sample PG A/ });
  });
});
