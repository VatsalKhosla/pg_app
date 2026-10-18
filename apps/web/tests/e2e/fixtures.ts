import { test as base, expect, type Page } from "@playwright/test";
import axe from "axe-core";

import { WCAG_22_AA } from "../wcag";

declare global {
  interface Window {
    __cspViolations?: string[];
    axe: typeof axe;
  }
}

interface Fixtures {
  /** Console errors a test expects, such as the browser's note about a 404 response. */
  expectedConsoleErrors: RegExp[];
  browserProblems: string[];
}

/**
 * Every test fails on unexpected browser console errors, uncaught exceptions and Content Security
 * Policy violations, whatever it was checking (BUILD_PLAN 0.5: no CSP violations in the console).
 */
export const test = base.extend<Fixtures>({
  expectedConsoleErrors: [[], { option: true }],
  browserProblems: [
    async ({ page, expectedConsoleErrors }, use) => {
      const problems: string[] = [];
      page.on("console", (message) => {
        const text = message.text();
        if (message.type() === "error" && !expectedConsoleErrors.some((re) => re.test(text))) {
          problems.push(`console error: ${text}`);
        }
      });
      page.on("pageerror", (error) => {
        problems.push(`uncaught: ${error.message}`);
      });
      // Runs before the page's own scripts, outside the page's policy (DevTools protocol).
      await page.addInitScript(() => {
        window.__cspViolations = [];
        document.addEventListener("securitypolicyviolation", (event) => {
          window.__cspViolations?.push(`${event.violatedDirective} blocked ${event.blockedURI}`);
        });
      });

      await use(problems);

      const violations = await page
        .evaluate(() => window.__cspViolations ?? [])
        .catch(() => [] as string[]);
      expect([...problems, ...violations.map((violation) => `CSP: ${violation}`)]).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** WCAG 2.2 AA violations on the current page, as found by axe. */
export async function wcagViolations(page: Page): Promise<string[]> {
  // Evaluated through the DevTools protocol, so the page's script policy doesn't apply.
  await page.evaluate(axe.source);
  return page.evaluate(async (tags) => {
    const results = await window.axe.run(document, { runOnly: { type: "tag", values: tags } });
    return results.violations.map(
      (violation) =>
        `${violation.id}: ${violation.help} (${violation.nodes.map((node) => node.target.join(" ")).join(", ")})`,
    );
  }, WCAG_22_AA);
}
