// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { showFieldErrors } from "@/lib/forms/field-errors";

interface Values {
  name: string;
  phone: string;
}

function invalid(errors: { pointer?: string | null; detail: string }[]): ApiError {
  return new ApiError({
    message: "Request is invalid",
    status: 422,
    code: "VALIDATION_ERROR",
    problem: {
      type: "about:blank",
      title: "Request is invalid",
      status: 422,
      code: "VALIDATION_ERROR",
      errors: errors.map((error) => ({ code: "invalid", ...error })),
    },
  });
}

describe("showFieldErrors", () => {
  it("puts each error the form has a field for next to it", () => {
    const setError = vi.fn();

    const shown = showFieldErrors<Values>(
      invalid([
        { pointer: "/name", detail: "Too long" },
        { pointer: "/somewhereElse", detail: "Unknown" },
        { pointer: null, detail: "No pointer" },
      ]),
      setError,
      (pointer) => (pointer === "/name" ? "name" : undefined),
    );

    expect(shown).toBe(true);
    expect(setError).toHaveBeenCalledExactlyOnceWith("name", { message: "Too long" });
  });

  it("says when none could be placed, so the form shows the error itself", () => {
    const setError = vi.fn();

    expect(showFieldErrors<Values>(new Error("offline"), setError, () => "name")).toBe(false);
    expect(
      showFieldErrors<Values>(
        invalid([{ pointer: "/other", detail: "x" }]),
        setError,
        () => undefined,
      ),
    ).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });
});
