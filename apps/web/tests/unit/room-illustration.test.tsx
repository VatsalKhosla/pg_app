import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RoomIllustration } from "@/components/pg/room-illustration";

function drawn(props: Partial<React.ComponentProps<typeof RoomIllustration>>) {
  const { container } = render(
    <RoomIllustration
      occupancy="single"
      ac={false}
      attachedBath={false}
      balcony={false}
      caption="Illustration of the beds"
      {...props}
    />,
  );
  return container;
}

describe("a room type's illustration", () => {
  it.each([
    ["single", "1"],
    ["double", "2"],
    ["triple", "3"],
    ["quad", "4"],
  ] as const)("draws as many beds as a %s room has", (occupancy, beds) => {
    expect(drawn({ occupancy }).querySelector("svg")?.getAttribute("data-beds")).toBe(beds);
  });

  it("shows only what the room has", () => {
    const plain = drawn({});
    for (const feature of ["ac", "bath", "balcony"]) {
      expect(plain.querySelector(`[data-feature="${feature}"]`)).toBeNull();
    }
    const full = drawn({ ac: true, attachedBath: true, balcony: true });
    for (const feature of ["ac", "bath", "balcony"]) {
      expect(full.querySelector(`[data-feature="${feature}"]`)).not.toBeNull();
    }
  });

  it("says it's an illustration, and keeps the drawing from screen readers", () => {
    const container = drawn({ caption: "Not a photo of this room" });
    expect(container.textContent).toContain("Not a photo of this room");
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });
});
