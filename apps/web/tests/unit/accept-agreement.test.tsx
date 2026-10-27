import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AcceptAgreement, type AcceptText } from "@/components/owner/accept-agreement";
import { ApiError } from "@/lib/api/errors";
import * as client from "@/lib/owner/client";

import { WCAG_22_AA } from "../wcag";

vi.mock("@/lib/owner/client", () => ({ acceptAgreement: vi.fn() }));
const router = { push: vi.fn(), replace: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const text: AcceptText = {
  agree: "I've read this owner agreement (version draft-1) and I accept it.",
  required: "Tick the box to accept the agreement.",
  submit: "Accept the agreement",
  submitting: "Accepting",
  errors: { generic: "Something went wrong.", RATE_LIMITED: "Too many tries." },
};
const HASH = "a".repeat(64);

function problem(status: number, code: string): ApiError {
  return new ApiError({ message: code, status, code });
}

function show() {
  return render(<AcceptAgreement version="draft-1" documentSha256={HASH} text={text} />);
}

describe("AcceptAgreement", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("ticks nothing for the owner, and accepts nothing until they tick the box", async () => {
    const { container } = show();

    const box = screen.getByRole<HTMLInputElement>("checkbox", { name: text.agree });
    expect(box.checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: text.submit }));

    await screen.findByText(text.required);
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(client.acceptAgreement).not.toHaveBeenCalled();
    const results = await axe.run(container, { runOnly: [...WCAG_22_AA] });
    expect(results.violations).toEqual([]);
  });

  it("accepts the version and text the owner was shown, then opens the owner area", async () => {
    vi.mocked(client.acceptAgreement).mockResolvedValue({
      version: "draft-1",
      documentSha256: HASH,
      acceptedAt: "2027-07-14T10:00:00Z",
      ip: "127.0.0.1",
      userAgent: null,
    });
    show();

    fireEvent.click(screen.getByRole("checkbox", { name: text.agree }));
    fireEvent.click(screen.getByRole("button", { name: text.submit }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/owner");
    });
    expect(client.acceptAgreement).toHaveBeenCalledWith({
      version: "draft-1",
      documentSha256: HASH,
    });
  });

  it("reloads with the new text when the agreement changed meanwhile", async () => {
    vi.mocked(client.acceptAgreement).mockRejectedValue(problem(409, "AGREEMENT_CHANGED"));
    show();

    fireEvent.click(screen.getByRole("checkbox", { name: text.agree }));
    fireEvent.click(screen.getByRole("button", { name: text.submit }));

    await waitFor(() => {
      expect(router.replace).toHaveBeenCalledWith("/owner/agreement?changed=1");
    });
    expect(router.push).not.toHaveBeenCalled();
  });

  it("says what went wrong otherwise", async () => {
    vi.mocked(client.acceptAgreement).mockRejectedValue(problem(429, "RATE_LIMITED"));
    show();

    fireEvent.click(screen.getByRole("checkbox", { name: text.agree }));
    fireEvent.click(screen.getByRole("button", { name: text.submit }));

    expect((await screen.findByRole("alert")).textContent).toBe("Too many tries.");
    expect(router.push).not.toHaveBeenCalled();
  });
});
