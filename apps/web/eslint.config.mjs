import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";
import tseslint from "typescript-eslint";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // Type-aware rules for all TypeScript: no `any`, exhaustive switches, safe promises.
    files: ["**/*.{ts,tsx,mts,cts}"],
    extends: [tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      "@typescript-eslint/consistent-type-imports": ["error", { fixStyle: "inline-type-imports" }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-import-type-side-effects": "error",
      "@typescript-eslint/switch-exhaustiveness-check": "error",
    },
  },
  {
    // Zod only through src/lib/forms/zod.ts, which keeps it from probing for eval: the
    // Content Security Policy forbids eval and reports even the probe as a violation.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/lib/forms/zod.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: [{ name: "zod", message: 'Import { z } from "@/lib/forms/zod" instead.' }] },
      ],
    },
  },
  // Last: turn off stylistic rules that Prettier owns.
  prettier,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Test output (Playwright's HTML report ships its own scripts).
    "playwright-report/**",
    "test-results/**",
    "coverage/**",
  ]),
]);
