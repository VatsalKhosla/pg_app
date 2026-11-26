import { expect, type Page } from "@playwright/test";

/** A mobile number nobody else in the run uses: ten digits starting 6 to 9. */
export function newMobile(): string {
  const digits = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10)).join("");
  return `9${digits}`;
}

/** A fictional address nobody else in the run uses. */
export function newEmail(who = "student"): string {
  return `${who}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}@example.com`;
}

/**
 * Ask for a code for `email` and type in the one the API "sent". The tests' API sends no mail: it
 * logs it, and the sign-in page shows the code, as a test site does (scripts/e2e-env.sh).
 */
export async function enterEmailAndCode(page: Page, email: string): Promise<void> {
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Email me a code" }).click();
  await expect(page.getByRole("heading", { name: "Enter the code" })).toBeVisible();
  const shown = await page.getByText(/here's yours: [0-9]{6}/u).textContent();
  const code = /here's yours: ([0-9]{6})/u.exec(shown ?? "")?.[1];
  if (code === undefined) throw new Error("the sign-in page showed no code");
  await page.getByLabel("Six-digit code", { exact: true }).fill(code);
  await page.getByRole("button", { name: "Continue" }).click();
}
