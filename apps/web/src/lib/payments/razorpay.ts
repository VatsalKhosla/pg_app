import { brand } from "@/config/brand";

import type { CheckoutCallback, PaymentStart } from "./client";

/**
 * Razorpay's Standard Checkout (https://razorpay.com/docs/payments/payment-gateway/web-integration/
 * standard/integration-steps/, read on 2026-11-05). Its script loads only when a student taps Pay.
 * The payment page's own policy allows what it needs (src/proxy.ts, next.config.ts; ADR 0056).
 */

const SCRIPT_URL = "https://checkout.razorpay.com/v1/checkout.js";

interface RazorpayAnswer {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  /** Seconds until checkout closes itself: the hold's time left. */
  timeout: number;
  prefill: { name?: string; contact: string };
  theme: { color: string };
  handler: (answer: RazorpayAnswer) => void;
  modal: { ondismiss: () => void };
}

interface RazorpayCheckout {
  open(): void;
}

type RazorpayConstructor = new (options: RazorpayOptions) => RazorpayCheckout;

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor;
  }
}

let loading: Promise<RazorpayConstructor> | undefined;

/** Razorpay's script, once per page. A failed load can be tried again. */
function loadCheckout(): Promise<RazorpayConstructor> {
  if (window.Razorpay !== undefined) return Promise.resolve(window.Razorpay);
  loading ??= new Promise<RazorpayConstructor>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.async = true;
    script.addEventListener("load", () => {
      if (window.Razorpay === undefined) {
        loading = undefined;
        reject(new Error("Razorpay's script loaded without its checkout"));
      } else {
        resolve(window.Razorpay);
      }
    });
    script.addEventListener("error", () => {
      loading = undefined;
      script.remove();
      reject(new Error("Razorpay's script couldn't load"));
    });
    document.head.append(script);
  });
  return loading;
}

/** How checkout ended: what it handed over for the API to check, or closed without paying. */
export type CheckoutEnd = { kind: "paid"; callback: CheckoutCallback } | { kind: "closed" };

/**
 * Opens checkout, which retries a failed attempt by itself while it's open. Rejects only when it
 * can't open at all. Its answer proves nothing yet: only the API's word moves the booking.
 */
export async function openRazorpayCheckout(
  start: PaymentStart,
  description: string,
): Promise<CheckoutEnd> {
  const Razorpay = await loadCheckout();
  return new Promise<CheckoutEnd>((resolve) => {
    new Razorpay({
      key: start.keyId,
      amount: start.amountPaise,
      currency: start.currency,
      name: brand.name,
      description,
      order_id: start.orderId,
      timeout: start.expiresInSeconds,
      prefill: {
        ...(start.prefill.name === null ? {} : { name: start.prefill.name }),
        contact: start.prefill.contact,
      },
      theme: { color: brand.colors.primary },
      handler: (answer) => {
        resolve({
          kind: "paid",
          callback: {
            providerPaymentId: answer.razorpay_payment_id,
            signature: answer.razorpay_signature,
          },
        });
      },
      modal: {
        ondismiss: () => {
          resolve({ kind: "closed" });
        },
      },
    }).open();
  });
}
