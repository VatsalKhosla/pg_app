import "react";

// Lets style objects set CSS custom properties (the brand colours on <html>) without casts.
// Merging into React's interface needs an index signature; a Record type can't merge.
declare module "react" {
  // eslint-disable-next-line @typescript-eslint/consistent-indexed-object-style
  interface CSSProperties {
    [customProperty: `--${string}`]: string | number | undefined;
  }
}
