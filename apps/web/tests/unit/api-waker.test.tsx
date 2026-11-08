import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiWaker } from "@/components/system/api-waker";
import { browserApi } from "@/lib/api/browser";

vi.mock("@/lib/api/browser", () => ({ browserApi: { GET: vi.fn() } }));

const WAKE = "https://api.example.test";

function answers(...statuses: number[]) {
  const get = vi.mocked(browserApi.GET);
  get.mockReset();
  for (const status of statuses) {
    get.mockResolvedValueOnce({ response: new Response(null, { status }) });
  }
}

describe("waking the test site's API", () => {
  const pings = vi.fn(() => Promise.resolve(new Response()));

  beforeEach(() => {
    pings.mockClear();
    vi.stubGlobal("fetch", pings);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does nothing when the API is awake", async () => {
    answers(200);
    const onAwake = vi.fn();
    render(<ApiWaker wakeUrl={WAKE} text="Waking" pollMs={1} onAwake={onAwake} />);

    await waitFor(() => {
      expect(browserApi.GET).toHaveBeenCalled();
    });
    expect(screen.queryByRole("status")).toBeNull();
    expect(pings).not.toHaveBeenCalled();
    expect(onAwake).not.toHaveBeenCalled();
  });

  it("wakes a sleeping API from the browser, says so, and reloads once it answers", async () => {
    answers(429, 429, 200);
    const onAwake = vi.fn();
    render(<ApiWaker wakeUrl={WAKE} text="Waking" pollMs={1} onAwake={onAwake} />);

    await screen.findByRole("status");
    expect(pings).toHaveBeenCalledWith(`${WAKE}/healthz`, { mode: "no-cors", cache: "no-store" });
    await waitFor(() => {
      expect(onAwake).toHaveBeenCalledTimes(1);
    });
  });
});
