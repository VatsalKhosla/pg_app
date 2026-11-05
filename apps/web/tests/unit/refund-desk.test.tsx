import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RefundAnswer, type RefundAnswerText } from "@/components/ops/refund-answer";
import { RefundDesk, type RefundDeskText } from "@/components/ops/refund-desk";
import { ApiError } from "@/lib/api/errors";
import * as payments from "@/lib/payments/client";

import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/payments/client", () => ({
  requestRefund: vi.fn(),
  approveRefund: vi.fn(),
  declineRefund: vi.fn(),
}));
const refresh = vi.fn();
vi.mock("@/components/ops/use-refresh", () => ({ useRefresh: () => refresh }));

const PAYMENT = "01933b1e-0000-7000-8000-000000000001";
const REFUND = "01933b1e-0000-7000-8000-000000000002";
const DESK: RefundDeskText = {
  open: "Give money back",
  title: "Give money back",
  amount: "Amount, in rupees",
  left: "Up to ₹2,000 of this payment can go back.",
  reason: "Why",
  needAmount: "Enter an amount up to what can go back.",
  needReason: "Say why, for the record.",
  next: "Next",
  confirmTitle: "Give {amount} back?",
  confirmBody: "It goes to the student's bank.",
  confirmWaits: "It waits for a second person.",
  yes: "Yes, go ahead",
  back: "Go back",
  close: "Close",
  sent: "It's on its way.",
  waits: "It's waiting for a second person.",
  tooMuch: "That's more than can go back.",
  failed: "That didn't work.",
};
const ANSWER: RefundAnswerText = {
  approve: "Approve and send it",
  decline: "Decline",
  declineTitle: "Decline this refund?",
  reason: "Why",
  needReason: "Say why, for the record.",
  confirmDecline: "Yes, decline it",
  back: "Go back",
  secondPerson: "You asked for this refund, so someone else has to approve it.",
  answered: "Someone has answered this refund already.",
  failed: "That didn't work.",
};

function apiError(status: number, code: string, detail: string) {
  return new ApiError({
    message: code,
    status,
    code,
    problem: { type: "about:blank", title: code, status, code, detail },
  });
}

function showDesk(refundablePaise = 200_000) {
  return render(
    <RefundDesk
      paymentId={PAYMENT}
      refundablePaise={refundablePaise}
      secondPersonAbovePaise={500_000}
      text={DESK}
    />,
  );
}

function open() {
  fireEvent.click(screen.getByRole("button", { name: DESK.open }));
}

function fill(amount: string, reason: string) {
  fireEvent.change(screen.getByLabelText(DESK.amount), { target: { value: amount } });
  fireEvent.change(screen.getByLabelText(DESK.reason), { target: { value: reason } });
  fireEvent.click(screen.getByRole("button", { name: DESK.next }));
}

describe("RefundDesk", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "a-key-for-this-refund" });
  });

  it("starts at what can go back, says what it will do, then sends it with a key", async () => {
    vi.mocked(payments.requestRefund).mockResolvedValue({ status: "requested" } as never);
    const { container } = showDesk();

    open();
    expect(screen.getByLabelText<HTMLInputElement>(DESK.amount).value).toBe("2000");
    expect((await axe.run(container, { runOnly: [...WCAG_22_AA] })).violations).toEqual([]);

    fill("1,500.50", "  The owner asked us to.  ");

    expect(screen.getByRole("heading", { name: "Give ₹1,500.50 back?" })).toBeTruthy();
    expect(screen.getByText(DESK.confirmBody)).toBeTruthy();
    expect(payments.requestRefund).not.toHaveBeenCalled();
    expect((await axe.run(container, { runOnly: [...WCAG_22_AA] })).violations).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: DESK.yes }));

    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe(DESK.sent);
    });
    expect(payments.requestRefund).toHaveBeenCalledWith(
      PAYMENT,
      150_050,
      "The owner asked us to.",
      "a-key-for-this-refund",
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("says it waits for a second person above the threshold", async () => {
    vi.mocked(payments.requestRefund).mockResolvedValue({ status: "awaiting_approval" } as never);
    showDesk(1_000_000);

    open();
    fill("5000.01", "A large one.");

    expect(screen.getByText(DESK.confirmWaits)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: DESK.yes }));
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe(DESK.waits);
    });
  });

  it.each([
    ["nothing", ""],
    ["words", "lots"],
    ["zero", "0"],
    ["more than is left", "2000.01"],
  ])("refuses %s as an amount", (_, amount) => {
    showDesk();

    open();
    fill(amount, "A reason.");

    expect(screen.getByText(DESK.needAmount)).toBeTruthy();
    expect(screen.queryByRole("button", { name: DESK.yes })).toBeNull();
  });

  it("needs a reason", () => {
    showDesk();

    open();
    fill("100", "   ");

    expect(screen.getByText(DESK.needReason)).toBeTruthy();
    expect(screen.queryByRole("button", { name: DESK.yes })).toBeNull();
  });

  it("goes back without sending, and closes", () => {
    showDesk();

    open();
    fill("100", "A reason.");
    fireEvent.click(screen.getByRole("button", { name: DESK.back }));
    fireEvent.click(screen.getByRole("button", { name: DESK.close }));

    expect(screen.getByRole("button", { name: DESK.open })).toBeTruthy();
    expect(payments.requestRefund).not.toHaveBeenCalled();
  });

  it("says why the API refused, and a new try is a new refund", async () => {
    vi.mocked(payments.requestRefund).mockRejectedValue(
      apiError(409, "REFUND_TOO_MUCH", "At most ₹500.00 of this payment can go back."),
    );
    showDesk();

    open();
    fill("100", "A reason.");
    fireEvent.click(screen.getByRole("button", { name: DESK.yes }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      `${DESK.tooMuch} At most ₹500.00 of this payment can go back.`,
    );
    expect(refresh).toHaveBeenCalled();
    expect(screen.getByLabelText<HTMLTextAreaElement>(DESK.reason).value).toBe("A reason.");
  });

  it("keeps its key through a failure that may pass, so a retry can't give back twice", async () => {
    vi.mocked(payments.requestRefund)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ status: "requested" } as never);
    const keys = ["first-key", "second-key"];
    vi.stubGlobal("crypto", { randomUUID: () => keys.shift() ?? "" });
    showDesk();

    open();
    fill("100", "A reason.");
    fireEvent.click(screen.getByRole("button", { name: DESK.yes }));
    expect((await screen.findByRole("alert")).textContent).toBe(DESK.failed);

    fireEvent.click(screen.getByRole("button", { name: DESK.next }));
    fireEvent.click(screen.getByRole("button", { name: DESK.yes }));

    await waitFor(() => {
      expect(payments.requestRefund).toHaveBeenCalledTimes(2);
    });
    expect(vi.mocked(payments.requestRefund).mock.calls.map((call) => call[3])).toEqual([
      "first-key",
      "first-key",
    ]);
  });
});

describe("RefundAnswer", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("approves, and passes axe", async () => {
    vi.mocked(payments.approveRefund).mockResolvedValue({} as never);
    const { container } = render(<RefundAnswer id={REFUND} text={ANSWER} />);

    expect((await axe.run(container, { runOnly: [...WCAG_22_AA] })).violations).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: ANSWER.approve }));

    await waitFor(() => {
      expect(refresh).toHaveBeenCalled();
    });
    expect(payments.approveRefund).toHaveBeenCalledWith(REFUND);
  });

  it("says when the person who asked tries to approve it", async () => {
    vi.mocked(payments.approveRefund).mockRejectedValue(
      apiError(409, "REFUND_NEEDS_SECOND_PERSON", "Someone else has to approve this refund."),
    );
    render(<RefundAnswer id={REFUND} text={ANSWER} />);

    fireEvent.click(screen.getByRole("button", { name: ANSWER.approve }));

    expect((await screen.findByRole("alert")).textContent).toBe(ANSWER.secondPerson);
    expect(screen.getByRole("button", { name: ANSWER.approve })).toBeTruthy();
  });

  it("says when someone else answered first", async () => {
    vi.mocked(payments.approveRefund).mockRejectedValue(
      apiError(409, "INVALID_TRANSITION", "This refund isn't waiting for an answer."),
    );
    render(<RefundAnswer id={REFUND} text={ANSWER} />);

    fireEvent.click(screen.getByRole("button", { name: ANSWER.approve }));

    expect((await screen.findByRole("alert")).textContent).toBe(ANSWER.answered);
    expect(refresh).toHaveBeenCalled();
  });

  it("declines with a reason, and needs one", async () => {
    vi.mocked(payments.declineRefund).mockResolvedValue({} as never);
    const { container } = render(<RefundAnswer id={REFUND} text={ANSWER} />);

    fireEvent.click(screen.getByRole("button", { name: ANSWER.decline }));
    expect((await axe.run(container, { runOnly: [...WCAG_22_AA] })).violations).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: ANSWER.confirmDecline }));
    expect(screen.getByText(ANSWER.needReason)).toBeTruthy();
    expect(payments.declineRefund).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(ANSWER.reason), { target: { value: " Not ours. " } });
    fireEvent.click(screen.getByRole("button", { name: ANSWER.confirmDecline }));

    await waitFor(() => {
      expect(payments.declineRefund).toHaveBeenCalledWith(REFUND, "Not ours.");
    });
  });

  it("goes back from declining, and says when it fails", async () => {
    vi.mocked(payments.declineRefund).mockRejectedValue(new Error("network"));
    render(<RefundAnswer id={REFUND} text={ANSWER} />);

    fireEvent.click(screen.getByRole("button", { name: ANSWER.decline }));
    fireEvent.click(screen.getByRole("button", { name: ANSWER.back }));
    expect(screen.getByRole("button", { name: ANSWER.approve })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: ANSWER.decline }));
    fireEvent.change(screen.getByLabelText(ANSWER.reason), { target: { value: "Not ours." } });
    fireEvent.click(screen.getByRole("button", { name: ANSWER.confirmDecline }));

    expect((await screen.findByRole("alert")).textContent).toBe(ANSWER.failed);
  });
});
