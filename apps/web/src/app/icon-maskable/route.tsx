import { ImageResponse } from "next/og";

import { BrandIcon } from "@/components/brand/brand-icon";

// The web manifest's maskable icon: Android crops it to its own shape, so the logo sits on white
// inside the safe zone. A route of its own rather than one of icon.tsx's sizes, which each become
// a favicon <link> tag. Drawn once, at build time.
export const dynamic = "force-static";

const SIZE = 512;

export function GET(): ImageResponse {
  return new ImageResponse(<BrandIcon size={SIZE} fill scale={0.76} />, {
    width: SIZE,
    height: SIZE,
  });
}
