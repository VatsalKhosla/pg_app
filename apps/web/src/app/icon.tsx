import { ImageResponse } from "next/og";

import { BrandIcon } from "@/components/brand/brand-icon";

// The favicon and the web manifest's icons (192 and 512 px are what Android needs to install the
// app), drawn from src/config/brand.ts and generated once at build time.
const iconSizes = [32, 192, 512] as const;

export function generateImageMetadata() {
  return iconSizes.map((size) => ({
    id: String(size),
    size: { width: size, height: size },
    contentType: "image/png",
  }));
}

export default async function Icon({ id }: { id: Promise<string> }) {
  const size = Number(await id);
  return new ImageResponse(<BrandIcon size={size} />, { width: size, height: size });
}
