// @vitest-environment node
import { describe, expect, it } from "vitest";

import { maskPhoneNumbers, maskPii } from "@/lib/pii";

// The same cases as the API's tests (apps/api/tests/unit/test_pii.py): both sides mask alike.
describe("maskPhoneNumbers", () => {
  it.each([
    "+919876543210",
    "+91 98765 43210",
    "+91-98765-43210",
    "919876543210",
    "9876543210",
    "98765 43210",
    "09876543210",
    "+14155550123",
  ])("masks %s to its last four digits", (phone) => {
    expect(maskPhoneNumbers(`OTP sent to ${phone} just now`)).toBe(
      `OTP sent to ******${phone.slice(-4)} just now`,
    );
  });

  it.each([
    "BK-7F3K2Q9M",
    "0192f6d4-8e1c-7c3a-9b1e-2f4a6c8e0b1d",
    "2026-10-18T14:12:56Z",
    "1234567890",
    "300000",
    "12345678901234",
  ])("leaves %s alone", (text) => {
    expect(maskPhoneNumbers(text)).toBe(text);
  });

  it("masks every number in a string, not just the first", () => {
    expect(maskPhoneNumbers("9876543210 or 9123456789")).toBe("******3210 or ******6789");
  });
});

describe("maskPii", () => {
  it("masks inside nested objects and arrays without touching other values", () => {
    const event = { user: { phone: "+919876543210" }, tags: ["9876543210", 7], extra: null };

    expect(maskPii(event)).toEqual({
      user: { phone: "******3210" },
      tags: ["******3210", 7],
      extra: null,
    });
    expect(event.user.phone).toBe("+919876543210");
  });
});
