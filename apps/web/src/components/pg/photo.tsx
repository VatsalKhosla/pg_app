import type { Schemas } from "@pg-platform/api-client";

type Media = Schemas["PublicMedia"];
type Rendition = Schemas["Rendition"];

/** The sizes the media pipeline makes, smallest first (apps/api media/domain/assets.py). */
const SIZES = ["card", "gallery", "full"] as const;

function srcSet(renditions: readonly Rendition[], contentType: string): string {
  return SIZES.flatMap((name) => {
    const found = renditions.find(
      (rendition) => rendition.name === name && rendition.contentType === contentType,
    );
    return found?.width == null ? [] : [`${found.url} ${String(found.width)}w`];
  }).join(", ");
}

/**
 * A listing photo at the size the screen needs, in AVIF or WebP (the pipeline makes both): plain
 * `<picture>` markup, so no image script runs on the page. The first photo is the page's largest
 * paint, so it loads at once; the rest wait until they're near the screen.
 */
export function Photo({
  media,
  alt,
  sizes,
  first = false,
  className,
}: {
  media: Media;
  alt: string;
  sizes: string;
  first?: boolean;
  className?: string;
}) {
  const fallback =
    media.renditions.find(
      (rendition) => rendition.name === "gallery" && rendition.contentType === "image/webp",
    ) ?? media.renditions.find((rendition) => rendition.contentType.startsWith("image/"));
  if (fallback === undefined) return null;
  return (
    <picture>
      <source type="image/avif" srcSet={srcSet(media.renditions, "image/avif")} sizes={sizes} />
      <source type="image/webp" srcSet={srcSet(media.renditions, "image/webp")} sizes={sizes} />
      <img
        src={fallback.url}
        alt={alt}
        width={fallback.width ?? undefined}
        height={fallback.height ?? undefined}
        loading={first ? "eager" : "lazy"}
        fetchPriority={first ? "high" : "auto"}
        decoding="async"
        className={className}
      />
    </picture>
  );
}
