import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Unit and component tests (`make test-web`). Components render in jsdom; files that test
// server-side code opt into the node environment with a `@vitest-environment node` comment.
export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["tests/unit/setup.ts"],
    restoreMocks: true,
    unstubEnvs: true,
  },
});
