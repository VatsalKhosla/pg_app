import { act, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CheckWindow } from "@/components/bookings/check-window";

import messages from "../../messages/en-IN.json";
import { WCAG_22_AA } from "../wcag";

const ENDS_AT = "2027-08-21T06:00:00Z";
const END = Date.parse(ENDS_AT);
const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;

function show() {
  return render(
    <NextIntlClientProvider locale="en-IN" messages={messages}>
      <CheckWindow endsAt={ENDS_AT} />
    </NextIntlClientProvider>,
  );
}

/** What it says once the browser has looked at its clock. */
function said(): string | null {
  act(() => {
    vi.advanceTimersByTime(0);
  });
  return screen.queryByRole("timer")?.textContent ?? null;
}

describe("CheckWindow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("says how long is left, never more than there is", () => {
    vi.setSystemTime(END - 23 * HOUR - 59 * MINUTE - 59 * SECOND);
    show();

    expect(said()).toBe("23 hours and 59 minutes left");
  });

  it("says nothing until the browser knows its own time, as the server can't", () => {
    vi.setSystemTime(END - 2 * HOUR);
    show();

    expect(screen.queryByRole("timer")).toBeNull();
  });

  it("keeps up as the time passes, down to its last minute and past it", () => {
    vi.setSystemTime(END - HOUR - MINUTE);
    show();
    expect(said()).toBe("1 hour and 1 minute left");

    act(() => {
      vi.advanceTimersByTime(MINUTE + 15 * SECOND);
    });
    expect(screen.getByRole("timer").textContent).toBe("59 minutes left");

    act(() => {
      vi.advanceTimersByTime(59 * MINUTE + 15 * SECOND);
    });
    expect(screen.getByRole("timer").textContent).toBe("Less than a minute left");

    act(() => {
      vi.advanceTimersByTime(30 * SECOND);
    });
    expect(screen.getByRole("timer").textContent).toBe(messages.Bookings.window.over);
  });

  it("is quiet for screen readers and passes axe", async () => {
    vi.setSystemTime(END - 5 * HOUR);
    const { container } = show();
    said();

    expect(screen.getByRole("timer").getAttribute("aria-live")).toBe("off");
    vi.useRealTimers();
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });
});
