import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingDesk } from "@/components/ops/booking-desk";
import { ApiError } from "@/lib/api/errors";
import * as ops from "@/lib/bookings/ops";
import type { OpsAction } from "@/lib/bookings/ops";

import messages from "../../messages/en-IN.json";
import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/bookings/ops", () => ({
  confirmForOwner: vi.fn(),
  rejectForOwner: vi.fn(),
  cancelForOwner: vi.fn(),
  recordMoveOut: vi.fn(),
  remindMoveIn: vi.fn(),
}));
const router = { refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const CODE = "BK-7F3K2Q9M";
const TODAY = "2027-12-01";
const REASON = "Spoke to the owner on the phone.";
const text = messages.Ops.bookings.actions;

type Reasoned = "confirm" | "reject" | "owner_cancel" | "move_out";

function show(actions: OpsAction[]) {
  return render(
    <NextIntlClientProvider locale="en-IN" messages={messages}>
      <BookingDesk code={CODE} actions={actions} today={TODAY} />
    </NextIntlClientProvider>,
  );
}

function choose(action: Reasoned, reason = REASON) {
  fireEvent.click(screen.getByRole("button", { name: text[action].label }));
  fireEvent.change(screen.getByLabelText(text.reason), { target: { value: reason } });
  fireEvent.click(screen.getByRole("button", { name: text.next }));
}

function title(action: Reasoned): string {
  return text[action].title.replace("{code}", CODE);
}

describe("BookingDesk", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("offers only what the API says ops may do now, and passes axe", async () => {
    const { container } = show(["confirm", "owner_cancel"]);

    expect(screen.getByRole("button", { name: text.confirm.label })).toBeTruthy();
    expect(screen.getByRole("button", { name: text.owner_cancel.label })).toBeTruthy();
    expect(screen.queryByRole("button", { name: text.reject.label })).toBeNull();
    expect(screen.queryByRole("button", { name: text.move_out.label })).toBeNull();
    expect(screen.queryByRole("button", { name: text.remind_move_in.label })).toBeNull();
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("needs a reason before a change", async () => {
    show(["reject"]);

    fireEvent.click(screen.getByRole("button", { name: text.reject.label }));
    fireEvent.click(screen.getByRole("button", { name: text.next }));

    expect(await screen.findByText(text.needReason)).toBeTruthy();
    expect(ops.rejectForOwner).not.toHaveBeenCalled();
  });

  it.each([
    ["confirm", ops.confirmForOwner],
    ["reject", ops.rejectForOwner],
    ["owner_cancel", ops.cancelForOwner],
  ] as const)("says what %s does, then sends it with the reason", async (action, call) => {
    vi.mocked(call).mockResolvedValue({} as never);
    show([action]);

    choose(action);
    expect(await screen.findByRole("heading", { name: title(action) })).toBeTruthy();
    expect(screen.getByText(text[action].body)).toBeTruthy();
    expect(call).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: text[action].yes }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalled();
    });
    expect(call).toHaveBeenCalledWith(CODE, REASON);
    expect(screen.getByRole("button", { name: text[action].label })).toBeTruthy();
  });

  it("records a move-out on the day ops give, today unless they change it", async () => {
    vi.mocked(ops.recordMoveOut).mockResolvedValue({} as never);
    show(["move_out"]);

    fireEvent.click(screen.getByRole("button", { name: text.move_out.label }));
    const day = screen.getByLabelText<HTMLInputElement>(text.moveOutDay);
    expect(day.value).toBe(TODAY);
    expect(day.max).toBe(TODAY);
    fireEvent.change(day, { target: { value: "2027-11-30" } });
    fireEvent.change(screen.getByLabelText(text.reason), { target: { value: REASON } });
    fireEvent.click(screen.getByRole("button", { name: text.next }));
    fireEvent.click(await screen.findByRole("button", { name: text.move_out.yes }));

    await waitFor(() => {
      expect(ops.recordMoveOut).toHaveBeenCalledWith(CODE, "2027-11-30", REASON);
    });
  });

  it("goes back without sending anything, and closes", async () => {
    show(["reject", "owner_cancel"]);

    choose("reject");
    fireEvent.click(await screen.findByRole("button", { name: text.back }));
    fireEvent.click(await screen.findByRole("button", { name: text.close }));

    expect(screen.getByRole("button", { name: text.owner_cancel.label })).toBeTruthy();
    expect(ops.rejectForOwner).not.toHaveBeenCalled();
  });

  it("says why the API refused, keeps the words typed, and looks again", async () => {
    vi.mocked(ops.recordMoveOut).mockRejectedValue(
      new ApiError({
        message: "refused",
        status: 409,
        code: "INVALID_TRANSITION",
        problem: {
          type: "about:blank",
          title: "That can't be done",
          status: 409,
          detail: "A move-out comes after the move-in.",
          code: "INVALID_TRANSITION",
        },
      }),
    );
    show(["move_out"]);

    choose("move_out");
    fireEvent.click(await screen.findByRole("button", { name: text.move_out.yes }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      `${text.refused} A move-out comes after the move-in.`,
    );
    expect(screen.getByLabelText<HTMLTextAreaElement>(text.reason).value).toBe(REASON);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("says so when a change fails", async () => {
    vi.mocked(ops.confirmForOwner).mockRejectedValue(new Error("network"));
    show(["confirm"]);

    choose("confirm");
    fireEvent.click(await screen.findByRole("button", { name: text.confirm.yes }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.failed);
  });

  it("asks a student to say they've moved in, one text a day", async () => {
    vi.mocked(ops.remindMoveIn)
      .mockResolvedValueOnce({ sent: true })
      .mockResolvedValueOnce({ sent: false });
    const { container } = show(["remind_move_in"]);

    expect(screen.getByText(text.remind_move_in.body)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: text.remind_move_in.label }));
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe(text.remind_move_in.sent);
    });

    fireEvent.click(screen.getByRole("button", { name: text.remind_move_in.label }));
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe(text.remind_move_in.already);
    });
    expect(ops.remindMoveIn).toHaveBeenCalledWith(CODE);
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("says why a nudge was refused, and looks again", async () => {
    vi.mocked(ops.remindMoveIn).mockRejectedValue(
      new ApiError({
        message: "refused",
        status: 409,
        code: "INVALID_TRANSITION",
        problem: {
          type: "about:blank",
          title: "That can't be done",
          status: 409,
          detail: "A checked-in booking can't be checked in.",
          code: "INVALID_TRANSITION",
        },
      }),
    );
    show(["remind_move_in"]);

    fireEvent.click(screen.getByRole("button", { name: text.remind_move_in.label }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      `${text.refused} A checked-in booking can't be checked in.`,
    );
    expect(router.refresh).toHaveBeenCalled();
  });
});
