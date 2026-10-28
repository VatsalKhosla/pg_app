import { brand, brandInitial } from "@/config/brand";

/** The size social sites show a link's picture at. */
export const OG_SIZE = { width: 1200, height: 630 } as const;

/**
 * A link's picture for social sites and chat apps (next/og's ImageResponse; step 3.6): the brand,
 * what the page is about and a few facts from live data, such as the lowest rent. Inline styles
 * and flexbox only, as next/og draws them; its own font has the rupee sign.
 */
export function OgCard({
  eyebrow,
  title,
  facts,
}: {
  eyebrow: string;
  title: string;
  facts: readonly string[];
}) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: "#ffffff",
        borderTop: `16px solid ${brand.colors.primary}`,
        padding: "56px 72px 64px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 16,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: brand.colors.primary,
            color: brand.colors.primaryForeground,
            fontSize: 44,
          }}
        >
          {brandInitial}
        </div>
        <div style={{ fontSize: 40, color: "#111827" }}>{brand.name}</div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ fontSize: 32, color: "#4b5563" }}>{eyebrow}</div>
        <div
          style={{
            fontSize: 68,
            lineHeight: 1.1,
            color: "#111827",
            maxHeight: 156,
            overflow: "hidden",
          }}
        >
          {title}
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 20 }}>
        {facts.map((fact) => (
          <div
            key={fact}
            style={{
              fontSize: 32,
              color: brand.colors.primary,
              border: `3px solid ${brand.colors.primary}`,
              borderRadius: 999,
              padding: "10px 28px",
            }}
          >
            {fact}
          </div>
        ))}
      </div>
    </div>
  );
}
