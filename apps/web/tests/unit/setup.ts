import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest doesn't expose test globals, so Testing Library can't clean up on its own.
afterEach(() => {
  cleanup();
});
