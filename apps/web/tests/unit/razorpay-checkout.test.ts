import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { brand } from "@/config/brand";
import type { PaymentStart } from "@/lib/payments/client";

const START: PaymentStart = {
  id: "01933b1e-0000-7000-8000-000000000001",
  provider: "razorpay",
  keyId: "rzp_test_1",
  orderId: "order_1",
  booking: "BK-7F3K2Q9M",
  amountPaise: 200_000,
  currency: "INR",
  expiresInSeconds: 600,
  prefill: { name: "A Student", contact: "+919000000000" },
  mode: "payment",
  customerId: null,
};
const DESCRIPTION = "Token for booking BK-7F3K2Q9M";

type Options = Record<string, unknown> & {
  handler: (answer: Record<string, string>) => void;
  modal: { ondismiss: () => void };
};

/** Razorpay's checkout, as far as the page can tell. */
function fakeRazorpay() {
  const opened: Options[] = [];
  const Razorpay = vi.fn(function Checkout(options: Options) {
    return {
      open() {
        opened.push(options);
      },
    };
  });
  return { Razorpay, opened };
}

async function loadModule() {
  vi.resetModules();
  return import("@/lib/payments/razorpay");
}

function scriptsAdded() {
  return document.head.querySelectorAll<HTMLScriptElement>(
    'script[src="https://checkout.razorpay.com/v1/checkout.js"]',
  );
}

describe("openRazorpayCheckout", () => {
  beforeEach(() => {
    delete window.Razorpay;
    for (const script of scriptsAdded()) script.remove();
  });

  afterEach(() => {
    delete window.Razorpay;
  });

  it("loads Razorpay's script only when asked, then opens checkout for the order", async () => {
    const { openRazorpayCheckout } = await loadModule();
    expect(scriptsAdded()).toHaveLength(0);
    const { Razorpay, opened } = fakeRazorpay();

    const ending = openRazorpayCheckout(START, DESCRIPTION);
    expect(scriptsAdded()).toHaveLength(1);
    window.Razorpay = Razorpay as never;
    scriptsAdded()[0]?.dispatchEvent(new Event("load"));
    await vi.waitFor(() => {
      expect(opened).toHaveLength(1);
    });

    expect(opened[0]).toMatchObject({
      key: "rzp_test_1",
      amount: 200_000,
      currency: "INR",
      name: brand.name,
      description: DESCRIPTION,
      order_id: "order_1",
      timeout: 600,
      prefill: { name: "A Student", contact: "+919000000000" },
    });

    opened[0]?.handler({
      razorpay_payment_id: "pay_1",
      razorpay_order_id: "order_1",
      razorpay_signature: "abc",
    });
    await expect(ending).resolves.toEqual({
      kind: "paid",
      callback: { providerPaymentId: "pay_1", signature: "abc" },
    });
  });

  it("opens a mandate's authorisation as a recurring payment for its customer", async () => {
    const { openRazorpayCheckout } = await loadModule();
    const { Razorpay, opened } = fakeRazorpay();
    window.Razorpay = Razorpay as never;

    void openRazorpayCheckout({ ...START, mode: "upi_mandate", customerId: "cust_1" }, DESCRIPTION);
    await vi.waitFor(() => {
      expect(opened).toHaveLength(1);
    });

    expect(opened[0]).toMatchObject({ recurring: 1, customer_id: "cust_1", order_id: "order_1" });
  });

  it("asks for no mandate when the token is a payment", async () => {
    const { openRazorpayCheckout } = await loadModule();
    const { Razorpay, opened } = fakeRazorpay();
    window.Razorpay = Razorpay as never;

    void openRazorpayCheckout(START, DESCRIPTION);
    await vi.waitFor(() => {
      expect(opened).toHaveLength(1);
    });

    expect(opened[0]).not.toHaveProperty("recurring");
    expect(opened[0]).not.toHaveProperty("customer_id");
  });

  it("uses the script it has, leaves out a name nobody gave, and says when checkout closes", async () => {
    const { openRazorpayCheckout } = await loadModule();
    const { Razorpay, opened } = fakeRazorpay();
    window.Razorpay = Razorpay as never;

    const ending = openRazorpayCheckout(
      { ...START, prefill: { name: null, contact: "+919000000000" } },
      DESCRIPTION,
    );
    await vi.waitFor(() => {
      expect(opened).toHaveLength(1);
    });

    expect(scriptsAdded()).toHaveLength(0);
    expect(opened[0]?.prefill).toEqual({ contact: "+919000000000" });
    opened[0]?.modal.ondismiss();
    await expect(ending).resolves.toEqual({ kind: "closed" });
  });

  it("rejects when the script can't load, and tries again the next time", async () => {
    const { openRazorpayCheckout } = await loadModule();

    const first = openRazorpayCheckout(START, DESCRIPTION);
    scriptsAdded()[0]?.dispatchEvent(new Event("error"));
    await expect(first).rejects.toThrow("couldn't load");
    expect(scriptsAdded()).toHaveLength(0);

    const second = openRazorpayCheckout(START, DESCRIPTION);
    expect(scriptsAdded()).toHaveLength(1);
    scriptsAdded()[0]?.dispatchEvent(new Event("load"));
    await expect(second).rejects.toThrow("without its checkout");
  });

  it("adds the script once for two tries at once", async () => {
    const { openRazorpayCheckout } = await loadModule();
    const { Razorpay, opened } = fakeRazorpay();

    void openRazorpayCheckout(START, DESCRIPTION);
    void openRazorpayCheckout(START, DESCRIPTION);
    expect(scriptsAdded()).toHaveLength(1);
    window.Razorpay = Razorpay as never;
    scriptsAdded()[0]?.dispatchEvent(new Event("load"));

    await vi.waitFor(() => {
      expect(opened).toHaveLength(2);
    });
  });
});
