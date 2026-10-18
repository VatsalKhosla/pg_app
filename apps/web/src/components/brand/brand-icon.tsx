import { brand, brandInitial } from "@/config/brand";

/**
 * The app icon for next/og's ImageResponse: the brand initial on a full-bleed primary square.
 * Full bleed suits every use: browsers show favicons as they are, while iOS and Android crop home
 * screen icons to their own shapes, so the letter stays inside the central safe zone.
 */
export function BrandIcon({ size }: { size: number }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: brand.colors.primary,
        color: brand.colors.primaryForeground,
        fontSize: Math.round(size * 0.6),
        fontWeight: 700,
        lineHeight: 1,
      }}
    >
      {brandInitial}
    </div>
  );
}
