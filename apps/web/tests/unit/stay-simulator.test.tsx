import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StaySimulator, type StaySimulatorProps } from "@/components/home/stay-simulator";

const props: StaySimulatorProps = {
  token: "₹1,234",
  stages: [
    { key: "find", title: "Find", body: "Browse.", place: 0 },
    { key: "reserve", title: "Reserve", body: "Hold your bed.", place: 1 },
    { key: "check", title: "Check the room", body: "Held for 36 hours.", place: 1 },
    { key: "settled", title: "Rent begins", body: "It counts toward your rent.", place: 2 },
  ],
  branches: [
    {
      key: "cancel",
      stages: ["reserve"],
      label: "I cancel",
      body: "Cancel for free up to 9 days before.",
    },
  ],
  text: {
    scrub: "Move through the steps",
    step: "Step {current} of {total}",
    places: ["With you", "Protected", "Counts toward your rent"],
    back: "Your token is back with you.",
    play: "Play",
    pause: "Pause",
    happens: "What if",
    onTrack: "Where your token is at this step.",
  },
};

function scrubTo(value: number) {
  fireEvent.change(screen.getByRole("slider", { name: "Move through the steps" }), {
    target: { value: String(value) },
  });
}

describe("the stay simulator", () => {
  it("shows only the figure and words it was given", () => {
    render(<StaySimulator {...props} />);

    expect(screen.getByText("₹1,234")).toBeTruthy();
    scrubTo(2);
    expect(screen.getByText("Held for 36 hours.")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/2,000|24 hours|7 days/u);
  });

  it("names the step for people using a screen reader", () => {
    render(<StaySimulator {...props} />);

    scrubTo(1);
    expect(
      screen.getByRole("slider", { name: "Move through the steps" }).getAttribute("aria-valuetext"),
    ).toBe("Reserve");
    expect(screen.getByText("Step 2 of 4")).toBeTruthy();
  });

  it("offers what can go wrong only where it can, and says where the token goes", () => {
    render(<StaySimulator {...props} />);

    expect(screen.queryByRole("button", { name: "I cancel" })).toBeNull();
    scrubTo(1);
    fireEvent.click(screen.getByRole("button", { name: "I cancel" }));

    expect(screen.getByText("Cancel for free up to 9 days before.")).toBeTruthy();
    expect(screen.getByText("Your token is back with you.")).toBeTruthy();
  });
});
