import { ImageResponse } from "next/og";

import { BrandIcon } from "@/components/brand/brand-icon";

// The home screen icon on iOS, which rounds the corners itself.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(<BrandIcon size={size.width} />, size);
}
