import { brand, brandInitial } from "@/config/brand";

/**
 * The app icon for next/og's ImageResponse: the brand initial on a full-bleed ink square, with the
 * sun going down in its corner. Full bleed suits every use: browsers show favicons as they are,
 * while iOS and Android crop home screen icons to their own shapes, so the letter stays inside the
 * central safe zone.
 */
export function BrandIcon({ size }: { size: number }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        position: "relative",
        alignItems: "center",
        justifyContent: "center",
        background: brand.colors.night,
        color: "#f3eee4",
        fontSize: Math.round(size * 0.56),
        fontWeight: 700,
        lineHeight: 1,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          right: Math.round(size * -0.14),
          bottom: Math.round(size * -0.2),
          width: Math.round(size * 0.62),
          height: Math.round(size * 0.62),
          borderRadius: "50%",
          background: brand.colors.sun,
        }}
      />
      <div style={{ display: "flex", position: "relative" }}>{brandInitial}</div>
    </div>
  );
}
