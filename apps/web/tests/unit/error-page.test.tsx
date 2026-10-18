import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ErrorPage from "@/app/error";
import { ErrorTextProvider } from "@/components/layout/error-text";

import messages from "../../messages/en-IN.json";

function renderError(error: Error & { digest?: string }, retry = vi.fn()) {
  render(
    <ErrorTextProvider text={messages.Error}>
      <ErrorPage error={error} retry={retry} />
    </ErrorTextProvider>,
  );
  return retry;
}

describe("ErrorPage", () => {
  it("explains, shows the error reference and retries on request", () => {
    const error = Object.assign(new Error("database unavailable"), { digest: "3141592653" });
    const retry = renderError(error);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Something went wrong");
    expect(screen.getByText("Error reference: 3141592653")).toBeDefined();
    expect(retry).toHaveBeenCalledOnce();
  });

  it("never shows the error's own message", () => {
    renderError(new Error("secret internal detail"));

    expect(screen.queryByText(/secret internal detail/)).toBeNull();
    expect(screen.queryByText(/Error reference/)).toBeNull();
  });

  it("needs the text from the root layout", () => {
    // React reports the error it rethrows; keep the test output quiet.
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(() => render(<ErrorPage error={new Error("x")} retry={vi.fn()} />)).toThrow(
      /ErrorTextProvider/,
    );
  });
});
