import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DisputeResolve } from "@/components/ops/dispute-resolve";
import { ApiError } from "@/lib/api/errors";
import * as disputes from "@/lib/disputes/client";
import type { OpsDispute } from "@/lib/disputes/client";

import messages from "../../messages/en-IN.json";
import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/disputes/client", () => ({ resolveDispute: vi.fn() }));
const router = { refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const ID = "01a190ce-8071-71a4-95fa-fdaf0d86fb0d";
const CODE = "BK-7F3K2Q9M";
const text = messages.Ops.disputes;
const NOTES = "Called the owner: the room was swapped.";

function show() {
  return render(
    <NextIntlClientProvider locale="en-IN" messages={messages}>
      <DisputeResolve id={ID} code={CODE} />
    </NextIntlClientProvider>,
  );
}

function choose(outcome: "refund" | "uphold") {
  fireEvent.click(screen.getByLabelText(text.outcomes[outcome]));
  fireEvent.change(screen.getByLabelText(text.notes), { target: { value: NOTES } });
  fireEvent.click(screen.getByRole("button", { name: text.next }));
}

describe("DisputeResolve", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("asks what ops found and passes axe", async () => {
    const { container } = show();

    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("needs an outcome and notes", async () => {
    show();

    fireEvent.click(screen.getByRole("button", { name: text.next }));

    expect(await screen.findByText(text.chooseOutcome)).toBeTruthy();
    expect(screen.getByText(text.needNotes)).toBeTruthy();
  });

  it.each(["refund", "uphold"] as const)(
    "confirms what %s means before it settles the dispute",
    async (outcome) => {
      vi.mocked(disputes.resolveDispute).mockResolvedValue({} as OpsDispute);
      show();

      choose(outcome);
      expect(
        await screen.findByRole("heading", {
          name: text.confirm[outcome].title.replace("{code}", CODE),
        }),
      ).toBeTruthy();
      expect(screen.getByText(text.confirm[outcome].body)).toBeTruthy();
      expect(disputes.resolveDispute).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: text.confirm[outcome].yes }));

      await waitFor(() => {
        expect(router.refresh).toHaveBeenCalled();
      });
      expect(disputes.resolveDispute).toHaveBeenCalledWith(ID, outcome, NOTES);
    },
  );

  it("goes back to the choice without settling anything", async () => {
    show();

    choose("refund");
    fireEvent.click(await screen.findByRole("button", { name: text.change }));

    expect(screen.getByRole("button", { name: text.next })).toBeTruthy();
    expect(disputes.resolveDispute).not.toHaveBeenCalled();
  });

  it("says so, and looks again, when someone settled it first", async () => {
    vi.mocked(disputes.resolveDispute).mockRejectedValue(
      new ApiError({ message: "settled", status: 409, code: "INVALID_TRANSITION" }),
    );
    show();

    choose("uphold");
    fireEvent.click(await screen.findByRole("button", { name: text.confirm.uphold.yes }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.settledAlready);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("says so when settling fails", async () => {
    vi.mocked(disputes.resolveDispute).mockRejectedValue(new Error("network"));
    show();

    choose("refund");
    fireEvent.click(await screen.findByRole("button", { name: text.confirm.refund.yes }));

    expect((await screen.findByRole("alert")).textContent).toBe(text.failed);
    expect(router.refresh).not.toHaveBeenCalled();
  });
});
