import { LOGO_DATA_URL } from "./logo-data";

/**
 * The app icons for next/og's ImageResponse, from the founders' logo: a teal house in a gold ring.
 *
 * - **Favicons and the manifest's "any" icons** keep the logo's own round shape, transparent
 *   around it, as browsers show them as they are.
 * - **A home screen icon** (`fill`) puts it on a white square that fills the icon, inside the
 *   safe zone: iOS fills transparency with black and rounds the corners itself, and Android masks
 *   a "maskable" icon to its own shape, keeping only a circle 80% across (`scale` 0.76).
 */
export function BrandIcon({
  size,
  fill = false,
  scale = 1,
}: {
  size: number;
  fill?: boolean;
  scale?: number;
}) {
  const logo = Math.round(size * scale);
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: fill ? "#ffffff" : "transparent",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- next/og draws plain img elements */}
      <img src={LOGO_DATA_URL} alt="" width={logo} height={logo} />
    </div>
  );
}
