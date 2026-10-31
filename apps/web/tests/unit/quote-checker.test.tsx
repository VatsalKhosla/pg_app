import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QuoteChecker, type QuoteCheckerText } from "@/components/pg/quote-checker";
import { ApiError } from "@/lib/api/errors";
import * as bookings from "@/lib/bookings/client";
import type { StudentBooking } from "@/lib/bookings/client";
import * as pricing from "@/lib/pricing/client";
import type { Quote } from "@/lib/pricing/client";

import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/pricing/client", () => ({ createQuote: vi.fn() }));
vi.mock("@/lib/bookings/client", () => ({ holdBed: vi.fn() }));
const router = { push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const VISIT = "01a190ce-8071-71a4-95fa-fdaf0d86fb0d";
const text: QuoteCheckerText = {
  room: "Room",
  chooseRoom: "Choose a room",
  moveIn: "Move-in date",
  stay: "How long you'd stay",
  submit: "Show my price",
  checking: "Checking…",
  needRoom: "Choose a room.",
  needDate: "Choose the day you'd move in.",
  monthly: "{amount} a month, fixed for your whole stay",
  token: "Token to reserve: {amount}",
  dueAtMoveIn: "Due when you move in: {amount}",
  deposit: "Security deposit: {amount}",
  charges: "Other charges: about {monthly} a month, and {once} once",
  noCharges: "No other charges.",
  validUntil: "This price holds until {time}.",
  bookingSoon: "Reserving a bed online opens soon.",
  errors: { generic: "We couldn't work out the price." },
  reserve: {
    note: "Reserving holds this bed for you while you pay the token.",
    submit: "Reserve this bed",
    reserving: "Reserving…",
    errors: {
      generic: "We couldn't reserve the bed.",
      VISIT_NOT_ON_SITE: "This can't be reserved from your visit:",
    },
  },
};

function quote(id: string): Quote {
  return {
    id,
    monthlyRentPaise: 1_000_000,
    tokenPaise: 200_000,
    dueAtMoveInPaise: 800_000,
    depositPaise: 1_000_000,
    monthlyChargesPaise: 0,
    oneTimeChargesPaise: 0,
    charges: [],
    explanation: "Base ₹10,000",
    expiresAt: "2027-07-14T10:30:00Z",
  } as unknown as Quote;
}

function show(visit: string | null = VISIT) {
  return render(
    <QuoteChecker
      rooms={[{ id: "room-1", label: "Double sharing" }]}
      stays={[{ value: 11, label: "11 months" }]}
      defaultStay={11}
      today="2027-07-14"
      visit={visit}
      text={text}
    />,
  );
}

async function priced() {
  fireEvent.click(screen.getByRole("button", { name: text.submit }));
  return screen.findByText("₹10,000 a month, fixed for your whole stay");
}

describe("QuoteChecker", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(pricing.createQuote).mockResolvedValue(quote("quote-1"));
  });

  it("offers no reservation away from a visit, only the price", async () => {
    show(null);

    await priced();

    expect(screen.queryByRole("button", { name: text.reserve.submit })).toBeNull();
    expect(screen.getByText(/Reserving a bed online opens soon/)).toBeTruthy();
  });

  it("reserves the bed at that price from the visit, then opens the booking", async () => {
    vi.mocked(bookings.holdBed).mockResolvedValue({ code: "BK-7F3K2Q9M" } as StudentBooking);
    const { container } = show();

    await priced();
    expect(screen.getByText(text.reserve.note)).toBeTruthy();
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: text.reserve.submit }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/bookings/BK-7F3K2Q9M");
    });
    expect(bookings.holdBed).toHaveBeenCalledWith("quote-1", VISIT, expect.any(String));
  });

  it("says why it couldn't, and a retry is the same reservation", async () => {
    vi.mocked(bookings.holdBed)
      .mockRejectedValueOnce(
        new ApiError({
          message: "late",
          status: 409,
          code: "VISIT_NOT_ON_SITE",
          problem: {
            type: "about:blank",
            title: "That visit can't take a reservation now",
            status: 409,
            detail: "Reserving on the spot is for the day of the visit.",
            code: "VISIT_NOT_ON_SITE",
          },
        }),
      )
      .mockRejectedValueOnce(new Error("network"));
    show();

    await priced();
    fireEvent.click(screen.getByRole("button", { name: text.reserve.submit }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "This can't be reserved from your visit: Reserving on the spot is for the day of the visit.",
    );
    fireEvent.click(screen.getByRole("button", { name: text.reserve.submit }));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe(text.reserve.errors.generic);
    });

    const keys = vi.mocked(bookings.holdBed).mock.calls.map((call) => call[2]);
    expect(keys[0]).toBe(keys[1]);
    expect(router.push).not.toHaveBeenCalled();
  });

  it("makes a new reservation for a new price", async () => {
    vi.mocked(bookings.holdBed).mockRejectedValue(new Error("network"));
    show();

    await priced();
    fireEvent.click(screen.getByRole("button", { name: text.reserve.submit }));
    await screen.findByRole("alert");
    vi.mocked(pricing.createQuote).mockResolvedValue(quote("quote-2"));
    await priced();
    fireEvent.click(screen.getByRole("button", { name: text.reserve.submit }));

    await waitFor(() => {
      expect(bookings.holdBed).toHaveBeenCalledTimes(2);
    });
    const [first, second] = vi.mocked(bookings.holdBed).mock.calls;
    expect(second?.[0]).toBe("quote-2");
    expect(second?.[2]).not.toBe(first?.[2]);
  });
});
