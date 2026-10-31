import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingActions, type BookingActionsText } from "@/components/bookings/booking-actions";
import { ApiError } from "@/lib/api/errors";
import { actionsFor } from "@/lib/bookings/actions";
import * as client from "@/lib/bookings/client";
import type { BookingStatus, StudentBooking } from "@/lib/bookings/client";

import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/bookings/client", () => ({ cancelMyBooking: vi.fn() }));
const router = { refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const text: BookingActionsText = {
  cancel: "Cancel this booking",
  confirmTitle: "Cancel booking BK-7F3K2Q9M?",
  refund: "You get your ₹2,000 token back in full.",
  policy: "Read the cancellation policy",
  confirm: "Yes, cancel it",
  keep: "Keep the booking",
  cancelling: "Cancelling…",
  changed: "What cancelling gives back has just changed.",
  failed: "That didn't work.",
  findAnother: "Find another PG",
};
const CODE = "BK-7F3K2Q9M";
const TOKEN = 200_000;

type Shown = Pick<StudentBooking, "code" | "status" | "cancellation">;

/** Each status with what the API says cancelling it now gives back (null: it can't be). */
const BOOKINGS: Record<BookingStatus, Shown["cancellation"]> = {
  held: { refundPaise: 0, late: false },
  token_secured: { refundPaise: TOKEN, late: false },
  confirmed: { refundPaise: TOKEN, late: false },
  checked_in: null,
  disputed: null,
  active: null,
  completed: null,
  expired: null,
  cancelled: null,
  rejected: null,
  no_show: null,
  refunded: null,
};

function show(status: BookingStatus) {
  const booking: Shown = { code: CODE, status, cancellation: BOOKINGS[status] };
  return render(<BookingActions booking={booking} policyPath="/refund-policy" text={text} />);
}

describe("BookingActions", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it.each(Object.keys(BOOKINGS) as BookingStatus[])(
    "offers what a %s booking allows, and nothing else",
    async (status) => {
      const { container } = show(status);
      const expected = actionsFor({ status, cancellation: BOOKINGS[status] });

      expect(screen.queryByRole("button", { name: text.cancel }) !== null).toBe(expected.cancel);
      expect(screen.queryByRole("link", { name: text.findAnother }) !== null).toBe(
        expected.findAnother,
      );
      const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
      expect(results.violations).toEqual([]);
    },
  );

  it("lets a student cancel only while they can, and find another PG once it ended early", () => {
    const can = (Object.keys(BOOKINGS) as BookingStatus[]).filter(
      (status) => actionsFor({ status, cancellation: BOOKINGS[status] }).cancel,
    );
    const other = (Object.keys(BOOKINGS) as BookingStatus[]).filter(
      (status) => actionsFor({ status, cancellation: BOOKINGS[status] }).findAnother,
    );

    expect(can).toEqual(["held", "token_secured", "confirmed"]);
    expect(other).toEqual(["expired", "cancelled", "rejected", "no_show", "refunded"]);
    expect(actionsFor({ status: "confirmed", cancellation: null }).contact).toBe(true);
    expect(actionsFor({ status: "token_secured", cancellation: null }).contact).toBe(false);
  });

  it("shows what cancelling gives back before it cancels, with the amount it was shown", async () => {
    vi.mocked(client.cancelMyBooking).mockResolvedValue({} as StudentBooking);
    show("confirmed");

    fireEvent.click(screen.getByRole("button", { name: text.cancel }));
    expect(screen.getByRole("heading", { name: text.confirmTitle })).toBeTruthy();
    expect(screen.getByText(text.refund)).toBeTruthy();
    expect(screen.getByRole("link", { name: text.policy }).getAttribute("href")).toBe(
      "/refund-policy",
    );
    expect(client.cancelMyBooking).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: text.confirm }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalled();
    });
    expect(client.cancelMyBooking).toHaveBeenCalledWith(CODE, TOKEN);
  });

  it("keeps the booking when the student changes their mind", () => {
    show("held");

    fireEvent.click(screen.getByRole("button", { name: text.cancel }));
    fireEvent.click(screen.getByRole("button", { name: text.keep }));

    expect(screen.getByRole("button", { name: text.cancel })).toBeTruthy();
    expect(client.cancelMyBooking).not.toHaveBeenCalled();
  });

  it("says so, and looks again, when what cancelling gives back has changed", async () => {
    vi.mocked(client.cancelMyBooking).mockRejectedValue(
      new ApiError({ message: "changed", status: 409, code: "REFUND_CHANGED" }),
    );
    show("held");

    fireEvent.click(screen.getByRole("button", { name: text.cancel }));
    fireEvent.click(screen.getByRole("button", { name: text.confirm }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.changed);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("says so when cancelling fails", async () => {
    vi.mocked(client.cancelMyBooking).mockRejectedValue(new Error("network"));
    show("token_secured");

    fireEvent.click(screen.getByRole("button", { name: text.cancel }));
    fireEvent.click(screen.getByRole("button", { name: text.confirm }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.failed);
    expect(router.refresh).not.toHaveBeenCalled();
  });
});
