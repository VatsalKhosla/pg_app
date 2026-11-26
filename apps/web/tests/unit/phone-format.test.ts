import { describe, expect, it } from "vitest";

import { formatPhone } from "@/lib/format/phone";

describe("a phone number as people read it", () => {
  it("groups an Indian mobile number in fives after the country code", () => {
    expect(formatPhone("+919891002696")).toBe("+91 98910 02696");
  });

  it("leaves any other number as it is", () => {
    expect(formatPhone("+4420794600")).toBe("+4420794600");
    expect(formatPhone("9891002696")).toBe("9891002696");
  });
});
