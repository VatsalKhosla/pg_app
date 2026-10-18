import { expect, test } from "./fixtures";

interface ManifestIcon {
  src: string;
  sizes: string;
  type: string;
  purpose: string;
}

/** Width and height from a PNG's header (the IHDR chunk). */
function pngSize(png: Buffer): string {
  expect(png.subarray(1, 4).toString("latin1")).toBe("PNG");
  return `${String(png.readUInt32BE(16))}x${String(png.readUInt32BE(20))}`;
}

test("the web app manifest makes the site installable", async ({ request }) => {
  const response = await request.get("/manifest.webmanifest");
  const manifest = (await response.json()) as {
    name: string;
    start_url: string;
    display: string;
    icons: ManifestIcon[];
  };

  expect(response.ok()).toBe(true);
  expect(manifest).toMatchObject({ name: "YourBrand", start_url: "/", display: "standalone" });
  expect(manifest.icons.map((icon) => `${icon.sizes} ${icon.purpose}`)).toEqual([
    "192x192 any",
    "512x512 any",
    "512x512 maskable",
  ]);
  for (const icon of manifest.icons) {
    const image = await request.get(icon.src);
    expect(image.headers()["content-type"]).toBe("image/png");
    expect(pngSize(await image.body())).toBe(icon.sizes);
  }
});

test("the page links its icons, manifest and theme colours", async ({ page, request }) => {
  await page.goto("/");

  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
    "href",
    "/manifest.webmanifest",
  );
  await expect(page.locator('meta[name="theme-color"]')).toHaveCount(2);
  const appleIcon = await page.locator('link[rel="apple-touch-icon"]').getAttribute("href");
  expect(appleIcon).not.toBeNull();
  expect(pngSize(await (await request.get(appleIcon ?? "")).body())).toBe("180x180");
});

test("robots.txt lets crawlers in outside staging", async ({ request }) => {
  const robots = await (await request.get("/robots.txt")).text();

  expect(robots).toContain("User-Agent: *");
  expect(robots).toContain("Allow: /");
});
