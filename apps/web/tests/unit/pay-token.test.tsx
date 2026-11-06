import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PayToken, type PayTokenText } from "@/components/bookings/pay-token";
import { ApiError } from "@/lib/api/errors";
import * as payments from "@/lib/payments/client";
import type { CheckoutCallback, PaymentStart } from "@/lib/payments/client";
import { openRazorpayCheckout } from "@/lib/payments/razorpay";

import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/payments/client", () => ({
  startTokenPayment: vi.fn(),
  finishCheckout: vi.fn(),
  checkMandate: vi.fn(),
  payAtTestBank: vi.fn(),
}));
vi.mock("@/lib/payments/razorpay", () => ({ openRazorpayCheckout: vi.fn() }));

const CODE = "BK-7F3K2Q9M";
const PATH = `/bookings/${CODE}`;
const TEXT: PayTokenText = {
  pay: "Pay ₹2,000",
  description: `Token for booking ${CODE}`,
  opening: "Opening the payment…",
  checking: "Checking your payment…",
  waiting: "Your bank hasn't finished yet.",
  blocking: "Your bank is still confirming the block.",
  checkAgain: "Check again",
  notPaid: "That payment didn't go through.",
  late: "Your payment came in after this booking had ended.",
  unverified: "We couldn't verify that payment.",
  changed: "This booking isn't waiting for its token any more.",
  failed: "Payments can't be reached right now.",
  backToBooking: "See your booking",
  test: {
    title: "A test payment",
    body: "No money moves.",
    pay: "Pay ₹2,000 at the test bank",
    cancel: "Not now",
  },
};
const CALLBACK: CheckoutCallback = { providerPaymentId: "pay_1", signature: "a".repeat(64) };

function startWith(provider: PaymentStart["provider"]): PaymentStart {
  return {
    id: "01933b1e-0000-7000-8000-000000000001",
    provider,
    keyId: "rzp_test_1",
    orderId: "order_1",
    booking: CODE,
    amountPaise: 200_000,
    currency: "INR",
    expiresInSeconds: 900,
    prefill: { name: "A Student", contact: "+919000000000" },
    mode: "payment",
    customerId: null,
  };
}

const assign = vi.fn();

function apiError(status: number, code: string) {
  return new ApiError({
    message: code,
    status,
    code,
    problem: { type: "about:blank", title: code, status, code },
  });
}

function show() {
  return render(<PayToken code={CODE} bookingPath={PATH} text={TEXT} />);
}

function tapPay() {
  fireEvent.click(screen.getByRole("button", { name: TEXT.pay }));
}

function razorpayPaid() {
  vi.mocked(payments.startTokenPayment).mockResolvedValue(startWith("razorpay"));
  vi.mocked(openRazorpayCheckout).mockResolvedValue({ kind: "paid", callback: CALLBACK });
}

describe("PayToken", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal("location", { href: `http://localhost:3000${PATH}/pay`, assign });
  });

  it("asks nothing of the gateway until the student taps, and passes axe", async () => {
    const { container } = show();

    expect(payments.startTokenPayment).not.toHaveBeenCalled();
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("opens Razorpay's checkout, has the API check its answer, then goes to the booking", async () => {
    razorpayPaid();
    vi.mocked(payments.finishCheckout).mockResolvedValue({ outcome: "paid", booking: CODE });
    show();

    tapPay();
    expect(screen.getByRole("status").textContent).toBe(TEXT.opening);

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(PATH);
    });
    expect(payments.startTokenPayment).toHaveBeenCalledWith(CODE);
    expect(openRazorpayCheckout).toHaveBeenCalledWith(startWith("razorpay"), TEXT.description);
    expect(payments.finishCheckout).toHaveBeenCalledWith(startWith("razorpay").id, CALLBACK);
    expect(payments.payAtTestBank).not.toHaveBeenCalled();
  });

  it("has the API ask the gateway about a block, whatever checkout handed over", async () => {
    vi.mocked(payments.startTokenPayment).mockResolvedValue({
      ...startWith("razorpay"),
      mode: "upi_mandate",
      customerId: "cust_1",
    });
    vi.mocked(openRazorpayCheckout).mockResolvedValue({ kind: "closed" });
    vi.mocked(payments.checkMandate).mockResolvedValue({ outcome: "paid", booking: CODE });
    show();

    tapPay();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(PATH);
    });
    expect(payments.checkMandate).toHaveBeenCalledWith(startWith("razorpay").id);
    expect(payments.finishCheckout).not.toHaveBeenCalled();
  });

  it("says the bank is still confirming a block, and asks again on request", async () => {
    vi.mocked(payments.startTokenPayment).mockResolvedValue({
      ...startWith("razorpay"),
      mode: "upi_mandate",
      customerId: "cust_1",
    });
    vi.mocked(openRazorpayCheckout).mockResolvedValue({ kind: "closed" });
    vi.mocked(payments.checkMandate).mockResolvedValue({ outcome: "waiting", booking: CODE });
    show();

    tapPay();

    expect(await screen.findByText(TEXT.blocking)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: TEXT.checkAgain }));
    await waitFor(() => {
      expect(vi.mocked(payments.checkMandate).mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("goes back to the button when the student closes checkout", async () => {
    vi.mocked(payments.startTokenPayment).mockResolvedValue(startWith("razorpay"));
    vi.mocked(openRazorpayCheckout).mockResolvedValue({ kind: "closed" });
    show();

    tapPay();

    expect(await screen.findByRole("button", { name: TEXT.pay })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(payments.finishCheckout).not.toHaveBeenCalled();
  });

  it("offers the test bank with the fake gateway, says no money moves, and passes axe", async () => {
    vi.mocked(payments.startTokenPayment).mockResolvedValue(startWith("fake"));
    vi.mocked(payments.payAtTestBank).mockResolvedValue(CALLBACK);
    vi.mocked(payments.finishCheckout).mockResolvedValue({ outcome: "paid", booking: CODE });
    const { container } = show();

    tapPay();

    const panel = await screen.findByRole("region", { name: TEXT.test.title });
    expect(panel.textContent).toContain(TEXT.test.body);
    expect(openRazorpayCheckout).not.toHaveBeenCalled();
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: TEXT.test.pay }));

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(PATH);
    });
    expect(payments.finishCheckout).toHaveBeenCalledWith(startWith("fake").id, CALLBACK);
  });

  it("leaves the test bank without paying", async () => {
    vi.mocked(payments.startTokenPayment).mockResolvedValue(startWith("fake"));
    show();

    tapPay();
    fireEvent.click(await screen.findByRole("button", { name: TEXT.test.cancel }));

    expect(screen.getByRole("button", { name: TEXT.pay })).toBeTruthy();
    expect(payments.payAtTestBank).not.toHaveBeenCalled();
  });

  it("says so when the test bank can't be reached", async () => {
    vi.mocked(payments.startTokenPayment).mockResolvedValue(startWith("fake"));
    vi.mocked(payments.payAtTestBank).mockRejectedValue(new Error("network"));
    show();

    tapPay();
    fireEvent.click(await screen.findByRole("button", { name: TEXT.test.pay }));

    expect((await screen.findByRole("alert")).textContent).toBe(TEXT.failed);
  });

  it("says when the booking isn't waiting any more, with the way back", async () => {
    vi.mocked(payments.startTokenPayment).mockRejectedValue(apiError(409, "INVALID_TRANSITION"));
    show();

    tapPay();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(TEXT.changed);
    expect(screen.getByRole("link", { name: TEXT.backToBooking }).getAttribute("href")).toBe(PATH);
  });

  it.each([
    ["the gateway is out of reach", apiError(503, "PAYMENT_GATEWAY_UNAVAILABLE")],
    ["the network failed", new Error("network")],
  ])("offers another try when %s", async (_, error) => {
    vi.mocked(payments.startTokenPayment).mockRejectedValue(error);
    show();

    tapPay();

    expect((await screen.findByRole("alert")).textContent).toBe(TEXT.failed);
    expect(screen.getByRole("button", { name: TEXT.pay })).toBeTruthy();
  });

  it("says when the script can't open checkout", async () => {
    vi.mocked(payments.startTokenPayment).mockResolvedValue(startWith("razorpay"));
    vi.mocked(openRazorpayCheckout).mockRejectedValue(new Error("blocked"));
    show();

    tapPay();

    expect((await screen.findByRole("alert")).textContent).toBe(TEXT.failed);
  });

  it("offers another try when the gateway says the payment failed", async () => {
    razorpayPaid();
    vi.mocked(payments.finishCheckout).mockResolvedValue({ outcome: "not_paid", booking: CODE });
    show();

    tapPay();

    expect((await screen.findByRole("alert")).textContent).toBe(TEXT.notPaid);
    expect(screen.getByRole("button", { name: TEXT.pay })).toBeTruthy();
    expect(assign).not.toHaveBeenCalled();
  });

  it("says when the money came in after the booking had moved on", async () => {
    razorpayPaid();
    vi.mocked(payments.finishCheckout).mockResolvedValue({ outcome: "late", booking: CODE });
    show();

    tapPay();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(TEXT.late);
    expect(screen.getByRole("link", { name: TEXT.backToBooking })).toBeTruthy();
    expect(assign).not.toHaveBeenCalled();
  });

  it.each([
    ["a signature the gateway didn't make", apiError(400, "PAYMENT_SIGNATURE_INVALID")],
    ["a payment that doesn't match", apiError(409, "PAYMENT_MISMATCH")],
  ])("doesn't ask again after %s", async (_, error) => {
    razorpayPaid();
    vi.mocked(payments.finishCheckout).mockRejectedValue(error);
    show();

    tapPay();

    expect((await screen.findByRole("alert")).textContent).toContain(TEXT.unverified);
    expect(payments.finishCheckout).toHaveBeenCalledTimes(1);
  });

  describe("while a bank finishes", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    async function settle(ms = 0) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
      });
    }

    it("keeps asking, a little less often each time, until it's paid", async () => {
      razorpayPaid();
      vi.mocked(payments.finishCheckout)
        .mockResolvedValueOnce({ outcome: "waiting", booking: CODE })
        .mockRejectedValueOnce(new Error("network"))
        .mockResolvedValueOnce({ outcome: "paid", booking: CODE });
      show();

      tapPay();
      await settle();
      expect(screen.getByRole("status").textContent).toBe(TEXT.waiting);
      expect(payments.finishCheckout).toHaveBeenCalledTimes(1);

      await settle(2_000);
      expect(payments.finishCheckout).toHaveBeenCalledTimes(2);
      expect(screen.getByRole("status").textContent).toBe(TEXT.waiting);
      expect(assign).not.toHaveBeenCalled();

      await settle(3_999);
      expect(payments.finishCheckout).toHaveBeenCalledTimes(2);
      await settle(1);
      expect(payments.finishCheckout).toHaveBeenCalledTimes(3);
      expect(assign).toHaveBeenCalledWith(PATH);
      vi.useRealTimers();
    });

    it("stops after a while, and the student can ask again themselves", async () => {
      razorpayPaid();
      vi.mocked(payments.finishCheckout).mockResolvedValue({ outcome: "waiting", booking: CODE });
      show();

      tapPay();
      await settle(60_000);
      expect(payments.finishCheckout).toHaveBeenCalledTimes(5);
      await settle(60_000);
      expect(payments.finishCheckout).toHaveBeenCalledTimes(5);

      vi.mocked(payments.finishCheckout).mockResolvedValue({ outcome: "paid", booking: CODE });
      fireEvent.click(screen.getByRole("button", { name: TEXT.checkAgain }));
      await settle();
      expect(assign).toHaveBeenCalledWith(PATH);
      vi.useRealTimers();
    });

    it("stops asking once the page has gone", async () => {
      razorpayPaid();
      vi.mocked(payments.finishCheckout).mockResolvedValue({ outcome: "waiting", booking: CODE });
      const { unmount } = show();

      tapPay();
      await settle();
      unmount();
      await settle(60_000);

      expect(payments.finishCheckout).toHaveBeenCalledTimes(1);
      vi.useRealTimers();
    });
  });
});
