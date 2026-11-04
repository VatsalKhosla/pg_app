import { describe, expect, it } from "vitest";

import { parseWaitMs } from "@/config/env";

describe("parseWaitMs", () => {
  it("is unset without a value", () => {
    expect(parseWaitMs("WAIT", undefined)).toBeUndefined();
    expect(parseWaitMs("WAIT", "")).toBeUndefined();
  });

  it("takes whole milliseconds and refuses anything else", () => {
    expect(parseWaitMs("WAIT", "90000")).toBe(90_000);
    for (const wrong of ["soon", "-1", "0", "1.5"]) {
      expect(() => parseWaitMs("WAIT", wrong)).toThrow("WAIT must be");
    }
  });
});
