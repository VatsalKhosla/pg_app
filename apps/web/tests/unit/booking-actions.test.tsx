import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingActions, type BookingActionsText } from "@/components/bookings/booking-actions";
import { ApiError } from "@/lib/api/errors";
import { actionsFor } from "@/lib/bookings/actions";
import * as client from "@/lib/bookings/client";
import type { BookingStatus, StudentBooking } from "@/lib/bookings/client";

import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/bookings/client", () => ({ cancelMyBooking: vi.fn(), checkInToMyBooking: vi.fn() }));
const router = { refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const text: BookingActionsText = {
  checkIn: {
    start: "I've moved in",
    title: "Have you moved in to A fictional PG?",
    body: "Say so once you're in the room. From then you have 24 hours to tell us if it isn't as shown.",
    confirm: "Yes, I've moved in",
    notYet: "Not yet",
    saving: "Saving…",
    changed: "This booking has just changed.",
  },
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

type Shown = Pick<StudentBooking, "code" | "status" | "cancellation" | "canCheckIn">;

/**
 * Each status with what the API says cancelling it now gives back (null: it can't be), and
 * whether the student may now say they've moved in: a confirmed booking from the day before the
 * move-in.
 */
const BOOKINGS: Record<BookingStatus, Pick<Shown, "cancellation" | "canCheckIn">> = {
  held: { cancellation: { refundPaise: 0, late: false }, canCheckIn: false },
  token_secured: { cancellation: { refundPaise: TOKEN, late: false }, canCheckIn: false },
  confirmed: { cancellation: { refundPaise: TOKEN, late: true }, canCheckIn: true },
  checked_in: { cancellation: null, canCheckIn: false },
  disputed: { cancellation: null, canCheckIn: false },
  active: { cancellation: null, canCheckIn: false },
  completed: { cancellation: null, canCheckIn: false },
  expired: { cancellation: null, canCheckIn: false },
  cancelled: { cancellation: null, canCheckIn: false },
  rejected: { cancellation: null, canCheckIn: false },
  no_show: { cancellation: null, canCheckIn: false },
  refunded: { cancellation: null, canCheckIn: false },
};
const STATUSES = Object.keys(BOOKINGS) as BookingStatus[];

function show(status: BookingStatus, shown: Partial<Shown> = {}) {
  const booking: Shown = { code: CODE, status, ...BOOKINGS[status], ...shown };
  return render(<BookingActions booking={booking} policyPath="/refund-policy" text={text} />);
}

describe("BookingActions", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it.each(STATUSES)("offers what a %s booking allows, and nothing else", async (status) => {
    const { container } = show(status);
    const expected = actionsFor({ status, ...BOOKINGS[status] });

    expect(screen.queryByRole("button", { name: text.checkIn.start }) !== null).toBe(
      expected.checkIn,
    );
    expect(screen.queryByRole("button", { name: text.cancel }) !== null).toBe(expected.cancel);
    expect(screen.queryByRole("link", { name: text.findAnother }) !== null).toBe(
      expected.findAnother,
    );
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("lets a student cancel only while they can, and find another PG once it ended early", () => {
    const allowed = (action: "checkIn" | "cancel" | "findAnother") =>
      STATUSES.filter((status) => actionsFor({ status, ...BOOKINGS[status] })[action]);

    expect(allowed("checkIn")).toEqual(["confirmed"]);
    expect(allowed("cancel")).toEqual(["held", "token_secured", "confirmed"]);
    expect(allowed("findAnother")).toEqual([
      "expired",
      "cancelled",
      "rejected",
      "no_show",
      "refunded",
    ]);
    const confirmed = { status: "confirmed", cancellation: null, canCheckIn: false } as const;
    expect(actionsFor(confirmed).contact).toBe(true);
    expect(actionsFor({ ...confirmed, status: "token_secured" }).contact).toBe(false);
  });

  it("offers no check-in on a confirmed booking until the API says it's open", () => {
    show("confirmed", { canCheckIn: false });

    expect(screen.queryByRole("button", { name: text.checkIn.start })).toBeNull();
    expect(screen.getByRole("button", { name: text.cancel })).toBeTruthy();
  });

  it("asks once more before it says the student has moved in, then shows the booking again", async () => {
    vi.mocked(client.checkInToMyBooking).mockResolvedValue({} as StudentBooking);
    show("confirmed");

    fireEvent.click(screen.getByRole("button", { name: text.checkIn.start }));
    expect(screen.getByRole("heading", { name: text.checkIn.title })).toBeTruthy();
    expect(screen.getByText(text.checkIn.body)).toBeTruthy();
    expect(client.checkInToMyBooking).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: text.checkIn.confirm }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalled();
    });
    expect(client.checkInToMyBooking).toHaveBeenCalledWith(CODE);
  });

  it("says nothing yet when the student hasn't moved in after all", () => {
    show("confirmed");

    fireEvent.click(screen.getByRole("button", { name: text.checkIn.start }));
    fireEvent.click(screen.getByRole("button", { name: text.checkIn.notYet }));

    expect(screen.getByRole("button", { name: text.checkIn.start })).toBeTruthy();
    expect(client.checkInToMyBooking).not.toHaveBeenCalled();
  });

  it("looks again when the booking changed before the student said so", async () => {
    vi.mocked(client.checkInToMyBooking).mockRejectedValue(
      new ApiError({ message: "changed", status: 409, code: "INVALID_TRANSITION" }),
    );
    show("confirmed");

    fireEvent.click(screen.getByRole("button", { name: text.checkIn.start }));
    fireEvent.click(screen.getByRole("button", { name: text.checkIn.confirm }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.checkIn.changed);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("says so when checking in fails", async () => {
    vi.mocked(client.checkInToMyBooking).mockRejectedValue(new Error("network"));
    show("confirmed");

    fireEvent.click(screen.getByRole("button", { name: text.checkIn.start }));
    fireEvent.click(screen.getByRole("button", { name: text.checkIn.confirm }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.failed);
    expect(router.refresh).not.toHaveBeenCalled();
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
