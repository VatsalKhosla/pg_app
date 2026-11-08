# Design

The site's visual world. Product truth is in `PRODUCT.md`, tokens are in `src/app/globals.css`, brand values are in `src/config/brand.ts`, and the token and contrast tables are in `docs/design/design-system.md`.

## The world: Delhi at golden hour
The founders chose this palette on 2026-11-08. The site is the hour when the sun goes down over a Delhi rooftop: water tanks, cables, neem trees, the elevated Metro, kites, and windows coming on.

- **Evening is a material, not a picture.** Ink fields (`scope-night`) carry whole regions: the hero, the budget band and the footer.
- **Ivory is where you read.** Lists, prices and policies sit on the ivory ground, in plain sections with hairlines between them.
- **Marigold is rationed.** The `sun` fill marks the one action that matters most on a screen (Find PGs, Book a visit) and the token itself.
- **Wayfinding is the graphic language.** Campuses and localities are Metro lines with station stops, and distances are drawn as lines to scale.

## Colour roles
| Role | Token | Use |
|---|---|---|
| Ink | `primary` (marigold in the dark theme) | Ordinary actions, links |
| Sun | `sun`, `sun-foreground` | The one main action; sliders; the token |
| Marigold | `marigold` | Marigold as text on ivory |
| Night | `night`, `scope-night` | Evening bands, in both themes |
| Neem | `neem` | Verified, safe, refundable |
| Dusk | `dusk` | Structure: the second Metro line, bed frames |
| Ember | `ember` | Sparingly: warmth in the scene |

- Neutrals lean warm in the light theme and toward the ink in the dark theme.
- Don't stack differently tinted cards down a page. One tinted panel, such as Safety, per page is plenty.

## Type
- **Eczar** (variable, OFL; designed by Vaibhav Singh for Latin and Devanagari together) sets headings on pages for students and parents. `text-hero` is for the home page's `h1` only.
- **Inter** sets text, forms and every figure.
  - Anything with a rupee sign stays in Inter: Eczar keeps that glyph in its Devanagari file, which is 85 KB an English page doesn't need.
- **Working tools** (`/owner`, `/ops`, `/field`, `/admin`, `/staff`) use Inter for headings too. Clarity and density come first there.
- No eyebrows or kickers above headings. No section numbers unless the order is the point.

## Shape and depth
- Large radii on big surfaces: `rounded-[2rem]` for panels, `rounded-b-[3.5rem]` for the hero, pills for search and chips.
- Glass (`glass`) only where something really passes behind it: the floating header, the hero's search, the phone's price bar. It goes solid without `backdrop-filter`.
- Shadows have an offset and a soft blur, tinted toward the ink.
- No coloured bars on cards, no decorative watermarks, no gradient text.

## Motion
One authored moment: **the sun sets as you scroll the home page.**
- It's CSS-only (scroll-driven animations). The sun sinks, the sky darkens, stars appear and windows come on.
- Everything that moves is a whole layer moved by `transform`, `translate` or `opacity`, so the compositor does it. Never animate inside an SVG.
- Beyond that, there are small state transitions, the search card's photo morphing into the PG page (`ViewTransition`), and a slight tilt on room illustrations under a pointer.
- All of it sits inside `prefers-reduced-motion: no-preference`. Reduced motion gets a still picture.

## Illustration and honesty
- Illustrations are labelled and never shown as a PG's photos. A listing shows only its own verified photos.
- The room viewer draws beds and features from the room type's own fields, and its caption says it's not a photo.
- Numbers come from the API or don't appear. Simulators use live policy figures and already-approved wording, and they never compute money.

## Signature components
- `components/home/dusk-scene.tsx`: the evening, as layers at depths.
- `components/home/hero-search.tsx`: the search capsule, a plain GET form that works without script.
- `components/home/stay-simulator.tsx`: where your token is at each step.
- `components/home/budget-explorer.tsx`: real PGs lit up by budget on a night map.
- `components/pg/room-illustration.tsx`: the isometric bed layout.
- The Metro-line place links and commute lines on the home and PG pages.
