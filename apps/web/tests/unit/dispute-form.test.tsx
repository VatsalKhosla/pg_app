import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DisputeForm } from "@/components/bookings/dispute-form";
import { ApiError } from "@/lib/api/errors";
import * as bookings from "@/lib/bookings/client";
import type { StudentBooking } from "@/lib/bookings/client";
import * as media from "@/lib/media/client";
import type { Media } from "@/lib/media/client";

import messages from "../../messages/en-IN.json";
import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/bookings/client", () => ({ openDispute: vi.fn() }));
vi.mock("@/lib/media/client", () => ({ upload: vi.fn() }));
const router = { refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const CODE = "BK-7F3K2Q9M";
const text = messages.Bookings.dispute;
const DESCRIPTION = "The listing showed a window; the room has none.";

function show() {
  return render(
    <NextIntlClientProvider locale="en-IN" messages={messages}>
      <DisputeForm code={CODE} />
    </NextIntlClientProvider>,
  );
}

function ready(id: string): Media {
  return {
    id,
    status: "ready",
    renditions: [{ name: "thumb", url: `https://storage.test/${id}.webp` }],
  } as unknown as Media;
}

function addPhotos(...names: string[]) {
  const input = screen.getByLabelText(text.addPhotos);
  fireEvent.change(input, {
    target: { files: names.map((name) => new File(["x"], name, { type: "image/jpeg" })) },
  });
}

function fillIn() {
  fireEvent.click(screen.getByLabelText(text.reasons.not_as_shown));
  fireEvent.change(screen.getByLabelText(text.description), { target: { value: DESCRIPTION } });
}

describe("DisputeForm", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("asks what's wrong and passes axe", async () => {
    const { container } = show();

    expect(screen.getByRole("heading", { name: text.title })).toBeTruthy();
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("sends nothing until it says what's wrong, in a few words", async () => {
    show();

    fireEvent.click(screen.getByRole("button", { name: text.send }));

    expect(await screen.findByText(text.needReason)).toBeTruthy();
    expect(screen.getByText(text.needDescription)).toBeTruthy();
    expect(bookings.openDispute).not.toHaveBeenCalled();
  });

  it("sends the report with the photos in their order, then shows the booking again", async () => {
    vi.mocked(media.upload)
      .mockResolvedValueOnce(ready("photo-1"))
      .mockResolvedValueOnce(ready("photo-2"));
    vi.mocked(bookings.openDispute).mockResolvedValue({} as StudentBooking);
    show();

    addPhotos("one.jpg", "two.jpg");
    expect(await screen.findByAltText("Photo 2")).toBeTruthy();
    fillIn();
    fireEvent.click(screen.getByRole("button", { name: text.send }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalled();
    });
    expect(media.upload).toHaveBeenCalledWith(
      "dispute_photo",
      expect.any(File),
      expect.any(Function),
    );
    expect(bookings.openDispute).toHaveBeenCalledWith(CODE, {
      reason: "not_as_shown",
      description: DESCRIPTION,
      photos: ["photo-1", "photo-2"],
    });
  });

  it("lets a photo go before sending", async () => {
    vi.mocked(media.upload).mockResolvedValueOnce(ready("photo-1"));
    vi.mocked(bookings.openDispute).mockResolvedValue({} as StudentBooking);
    show();

    addPhotos("one.jpg");
    fireEvent.click(await screen.findByRole("button", { name: "Remove photo 1" }));
    fillIn();
    fireEvent.click(screen.getByRole("button", { name: text.send }));

    await waitFor(() => {
      expect(bookings.openDispute).toHaveBeenCalled();
    });
    expect(vi.mocked(bookings.openDispute).mock.calls[0]?.[1].photos).toEqual([]);
  });

  it("says why a photo couldn't be added", async () => {
    vi.mocked(media.upload).mockResolvedValueOnce({
      id: "photo-1",
      status: "rejected",
      rejectionReason: "that isn't a photo",
      renditions: [],
    } as unknown as Media);
    show();

    addPhotos("one.jpg");

    expect(await screen.findByText("one.jpg couldn't be added: that isn't a photo")).toBeTruthy();
  });

  it("says so, and looks again, once the time to report has passed", async () => {
    vi.mocked(bookings.openDispute).mockRejectedValue(
      new ApiError({ message: "late", status: 409, code: "INVALID_TRANSITION" }),
    );
    show();

    fillIn();
    fireEvent.click(screen.getByRole("button", { name: text.send }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.tooLate);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("says when a photo is refused", async () => {
    vi.mocked(bookings.openDispute).mockRejectedValue(
      new ApiError({ message: "refused", status: 422, code: "DISPUTE_INVALID" }),
    );
    show();

    fillIn();
    fireEvent.click(screen.getByRole("button", { name: text.send }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.photosRefused);
    expect(router.refresh).not.toHaveBeenCalled();
  });
});
