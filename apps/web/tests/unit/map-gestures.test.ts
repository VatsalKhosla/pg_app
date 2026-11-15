import { describe, expect, it } from "vitest";

import { cooperative } from "@/components/map/gestures";

describe("cooperative", () => {
  it("lets a mouse's wheel zoom every map, without Ctrl or ⌘", () => {
    expect(cooperative("in-page", true)).toBe(false);
    expect(cooperative("fills-screen", true)).toBe(false);
  });

  it("leaves one finger to the page around a map on a touch screen", () => {
    expect(cooperative("in-page", false)).toBe(true);
  });

  it("lets one finger move a map that fills the screen, with no page to scroll past it", () => {
    expect(cooperative("fills-screen", false)).toBe(false);
  });
});
