import { ImageResponse } from "next/og";

import { BrandIcon } from "@/components/brand/brand-icon";

// The home screen icon on iOS, which rounds the corners itself and fills transparency with black:
// the logo on white, clear of the rounded corners.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(<BrandIcon size={size.width} fill scale={0.84} />, size);
}
