import { expect, test } from "./fixtures";

function nonceOf(policy: string | undefined): string | undefined {
  return /'nonce-([^']+)'/.exec(policy ?? "")?.[1];
}

test("pages carry a strict, per-request Content Security Policy and the security headers", async ({
  page,
}) => {
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  const policy = headers["content-security-policy"];

  expect(response?.status()).toBe(200);
  expect(policy).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic';/);
  expect(policy).not.toMatch(/script-src[^;]*'unsafe-inline'/);
  expect(policy).not.toContain("'unsafe-eval'");
  expect(policy).toContain("frame-ancestors 'none'");
  expect(policy).toContain("object-src 'none'");
  expect(headers).toMatchObject({
    "strict-transport-security": "max-age=63072000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "cross-origin-opener-policy": "same-origin",
  });
  expect(headers["permissions-policy"]).toContain("geolocation=(self)");
  expect(headers["permissions-policy"]).toContain("camera=()");
  expect(headers).not.toHaveProperty("x-powered-by");
});

test("every script carries the response's nonce, and the nonce changes per request", async ({
  page,
}) => {
  const first = nonceOf((await page.goto("/"))?.headers()["content-security-policy"]);
  // Browsers hide nonce attributes from the DOM; the nonce property still holds the value.
  const scriptNonces = await page
    .locator("script")
    .evaluateAll((scripts) => scripts.map((script) => (script as HTMLScriptElement).nonce));
  const second = nonceOf((await page.goto("/"))?.headers()["content-security-policy"]);

  expect(scriptNonces.length).toBeGreaterThan(0);
  expect(new Set(scriptNonces)).toEqual(new Set([first]));
  expect(second).not.toBe(first);
});
