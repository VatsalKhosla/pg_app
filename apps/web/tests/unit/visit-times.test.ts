import { describe, expect, it } from "vitest";

import { DAYS_AHEAD, indiaDate, visitDays, visitStart, visitTimes } from "@/lib/visits/times";

describe("the times a student may offer", () => {
  it("are the next two weeks of days in India, from today there", () => {
    // 11:30 pm in India on 14 July, though it's still the 14th in UTC too.
    const now = new Date("2027-07-14T18:00:00Z");
    const days = visitDays(now);

    expect(indiaDate(now)).toBe("2027-07-14");
    expect(days).toHaveLength(DAYS_AHEAD);
    expect(days[0]).toBe("2027-07-14");
    expect(days.at(-1)).toBe("2027-07-27");
    // Past midnight in India it's the next day, though not yet in UTC.
    expect(visitDays(new Date("2027-07-14T19:00:00Z"))[0]).toBe("2027-07-15");
  });

  it("start on the hour or half past, from 9 am to 7 pm", () => {
    const times = visitTimes();

    expect(times[0]).toBe("09:00");
    expect(times[1]).toBe("09:30");
    expect(times.at(-1)).toBe("19:00");
    expect(times).toHaveLength(21);
  });

  it("go to the API as instants, read as India time", () => {
    expect(visitStart("2027-07-15", "11:00")).toBe("2027-07-15T05:30:00.000Z");
  });
});
