# Design system

This document records the tokens, typography, motion and UI primitives of the site. The visual world behind them is in [`apps/web/DESIGN.md`](../../apps/web/DESIGN.md), and the references it draws on are in [`inspiration.md`](inspiration.md).

## 1. Colour and contrast

The founders chose Golden hour on 2026-11-08: deep ink, marigold and ivory. Brand colours live only in [`apps/web/src/config/brand.ts`](../../apps/web/src/config/brand.ts) and reach CSS through `brandStyle` (`--brand-*` custom properties on `<html>`). Semantic tokens and tints live in [`apps/web/src/app/globals.css`](../../apps/web/src/app/globals.css).

Every text pair meets at least 4.5:1, and control outlines (`--input`) and focus rings (`--ring`) at least 3:1 (WCAG 2.2 AA), in both themes. `tests/unit/brand-contrast.test.ts` checks the pairs, so a colour change that breaks one fails the build.

| Token pair | Light | Ratio | Dark | Ratio |
| --- | --- | --- | --- | --- |
| `--foreground` on `--background` | `#161a22` on `#fbf8f2` | 16.4:1 | `#f2eee6` on `#0d1119` | 16.3:1 |
| `--foreground` on `--surface` | `#161a22` on `#f5f1e8` | 15.5:1 | `#f2eee6` on `#121825` | 15.3:1 |
| `--foreground` on `--surface-warm` | `#161a22` on `#f1eadc` | 14.6:1 | `#f2eee6` on `#161d2b` | 14.6:1 |
| `--foreground` on `--card` | `#161a22` on `#ffffff` | 17.4:1 | `#f2eee6` on `#171e2c` | 14.4:1 |
| `--muted-foreground` on `--background` | `#5a5f6c` on `#fbf8f2` | 6.0:1 | `#aab0be` on `#0d1119` | 8.7:1 |
| `--muted-foreground` on `--surface-warm` | `#5a5f6c` on `#f1eadc` | 5.3:1 | `#aab0be` on `#161d2b` | 7.8:1 |
| `--muted-foreground` on `--muted` | `#5a5f6c` on `#f0ebe0` | 5.4:1 | `#aab0be` on `#1d2433` | 7.1:1 |
| `--primary-foreground` on `--primary` | `#ffffff` on `#1e2b45` | 14.1:1 | `#1a1204` on `#f2b24c` | 9.9:1 |
| `--primary` on `--background` | `#1e2b45` on `#fbf8f2` | 13.3:1 | `#f2b24c` on `#0d1119` | 10.1:1 |
| `--sun-foreground` on `--sun` | `#1e1405` on `#f0a93b` | 9.0:1 | `#1a1204` on `#f2b24c` | 9.9:1 |
| `--marigold` on `--background` | `#a55f00` on `#fbf8f2` | 4.7:1 | `#f5c46e` on `#0d1119` | 11.7:1 |
| `--ember` on `--background` | `#b2431f` on `#fbf8f2` | 5.3:1 | `#ff9d7d` on `#0d1119` | 9.3:1 |
| `--dusk` on `--background` | `#34466f` on `#fbf8f2` | 8.8:1 | `#a9bbe3` on `#0d1119` | 9.8:1 |
| `--neem` on `--background` | `#256b4c` on `#fbf8f2` | 6.0:1 | `#7cd3a6` on `#0d1119` | 10.6:1 |
| `--ember-soft-foreground` on `--ember-soft` | `#7a2a12` on `#fbeee6` | 8.5:1 | `#ffb49c` on `#2c1711` | 9.9:1 |
| `--marigold-soft-foreground` on `--marigold-soft` | `#673a00` on `#fdf0d9` | 8.5:1 | `#fad28c` on `#2a2010` | 11.2:1 |
| `--dusk-soft-foreground` on `--dusk-soft` | `#1e2b45` on `#e9edf5` | 12.0:1 | `#c8d5f0` on `#182136` | 10.9:1 |
| `--neem-soft-foreground` on `--neem-soft` | `#164a33` on `#e6f3ea` | 8.9:1 | `#9ee7bf` on `#11281d` | 10.9:1 |
| `--destructive-foreground` on `--destructive` | `#ffffff` on `#b3261e` | 6.5:1 | `#1a0d0b` on `#f38a80` | 7.9:1 |
| `--destructive` on `--background` | `#b3261e` on `#fbf8f2` | 6.2:1 | `#f38a80` on `#0d1119` | 7.9:1 |
| `--destructive-soft-foreground` on `--destructive-soft` | `#9b2019` on `#fbeae7` | 6.9:1 | `#f7b1a9` on `#3a1a17` | 8.8:1 |
| `--success` on `--background` | `#1f6b49` on `#fbf8f2` | 6.1:1 | `#7cd3a6` on `#0d1119` | 10.6:1 |
| `--success-soft-foreground` on `--success-soft` | `#1b5f41` on `#e3f2e8` | 6.6:1 | `#93dfb6` on `#12291e` | 9.9:1 |
| `--warning-soft-foreground` on `--warning-soft` | `#6f4300` on `#fdf0d3` | 7.5:1 | `#f4cf86` on `#2e2311` | 10.3:1 |
| `--night-foreground` on `--night` | `#f3eee4` on `#121827` | 15.3:1 | `#f2eee6` on `#080b11` | 17.0:1 |
| `--night-muted` on `--night` | `#b9bfcc` on `#121827` | 9.6:1 | `#a9afbd` on `#080b11` | 9.0:1 |
| `--night-accent` on `--night` | `#f5b451` on `#121827` | 9.7:1 | `#f5b451` on `#080b11` | 10.8:1 |
| `--input` (control border) on `--background` | `#868277` on `#fbf8f2` | 3.6:1 | `rgb(255 255 255 / 36%)` on `#0d1119` | 3.3:1 |

Two scopes change what the tokens mean inside them:
- **`scope-night`** makes a section an ink field in both themes: text, muted text, buttons, borders and focus rings all follow. Primary actions inside it are marigold.
- **`glass`** is frosted glass for a surface something passes behind. Where `backdrop-filter` isn't available it goes solid, so text keeps its contrast.

## 2. Typography

Loaded via `next/font/google` in [`apps/web/src/app/layout.tsx`](../../apps/web/src/app/layout.tsx), self-hosted at build time, with `display: "swap"`:

- **Sans (`--font-sans`):** `Inter` (variable, Latin preloaded), for body copy, form controls, tables and every figure. Anything with a rupee sign stays in Inter: Eczar keeps that glyph in its Devanagari file.
- **Display (`--font-display`):** `Eczar` at one static weight (500, not preloaded), applied to `h1`, `h2` and `h3` in the base layer and available through `font-display`. `font-synthesis-weight: none` keeps a heading from being smeared bold.
- **Working tools** (`/owner`, `/ops`, `/field`, `/admin`) take the `working-type` utility, which sets their headings in Inter too.

Fluid display scale in `@theme inline`:

- `text-hero`: `clamp(3rem, 1.75rem + 6.2vw, 6rem)`, line-height `0.98`, tracking `-0.025em`; the home page's `h1` only
- `text-display`: `clamp(2.25rem, 1.65rem + 3vw, 4rem)`, line-height `1.05`, tracking `-0.03em`
- `text-title-1`: `clamp(1.75rem, 1.5rem + 1.25vw, 2.5rem)`, line-height `1.12`, tracking `-0.025em`
- `text-title-2`: `clamp(1.375rem, 1.25rem + 0.7vw, 1.875rem)`, line-height `1.2`, tracking `-0.02em`
- `text-title-3`: `1.25rem`, line-height `1.3`, tracking `-0.015em`

## 3. Space, radius and elevation

- **Layout rhythm:** `px-gutter` (`clamp(1rem, 0.6rem + 2vw, 2.5rem)`), `py-section` (`clamp(3rem, 2rem + 5vw, 6.5rem)`), `max-w-page` (`78rem`) and `max-w-prose` (`42rem`).
- **Radius scale:** controls use `rounded-lg` (`0.75rem`), cards use `rounded-xl` (`1rem`), larger panels use `rounded-2xl` (`1.25rem`) and sheets/hero surfaces use `rounded-3xl` (`1.75rem`).
- **Layered shadows:** `--shadow-2xs` through `--shadow-xl` combine a tight contact shadow and a soft ambient shadow tinted with `--shadow-tint` (`22 26 34` in light mode, `0 0 0` at 3× strength in dark mode).

## 4. Motion

- **Curves:** `ease-standard` (`cubic-bezier(0.2, 0, 0, 1)`), `ease-emphasized` (`cubic-bezier(0.16, 1, 0.3, 1)`) for entrances, and `ease-exit` (`cubic-bezier(0.3, 0, 0.8, 0.15)`) for exits.
- **Durations:** `--duration-fast` (`120ms`), `--duration-base` (`200ms`), `--duration-slow` (`320ms`), `--duration-slower` (`480ms`).
- **Keyframe utilities:** `animate-rise` and `animate-fade`.
- **The evening scene:** the home page's sunset runs on CSS scroll-driven animations, and everything that moves is a whole layer moved by `transform`, `translate` or `opacity`.
- **Reduced motion (WCAG 2.3.3):** `@media (prefers-reduced-motion: reduce)` disables smooth scrolling, collapses animation and transition durations/delays to `0.01ms` / `0s`, and turns off view-transition animations.

## 5. Primitives (`apps/web/src/components/ui`)

- [`button.tsx`](../../apps/web/src/components/ui/button.tsx): `default`, `sun` (the marigold fill, for the one action that matters most on a screen), `soft`, `destructive`, `outline`, `secondary`, `ghost` and `link` variants; `default`, `sm`, `lg`, `icon`, `icon-sm` and `icon-lg` sizes; `default` and `pill` shapes. Touch targets are 44 px tall (`h-11`, `size-11`) on coarse pointers and tighten to 40 px (`pointer-fine:h-10`) under a mouse so owner and ops screens stay compact. Every size including `sm` and `link` stays at or above 24×24 px (WCAG 2.5.8).
- [`input.tsx`](../../apps/web/src/components/ui/input.tsx) & [`fields.tsx`](../../apps/web/src/components/ui/fields.tsx): shared `controlClasses` with a 3:1 `--input` border, 16 px text on phones (preventing iOS zoom on focus), 44 px touch height (`pointer-fine:h-10`), and a 2 px focus ring (`border-ring` + `ring-1 ring-ring`). `Choices` highlights the checked radio card with `border-primary`, `bg-primary-soft` and `ring-1 ring-primary` so selection never relies on colour alone (WCAG 1.4.1).
- [`sheet.tsx`](../../apps/web/src/components/ui/sheet.tsx): Radix Dialog drawer with `ease-emphasized` entrance, `ease-exit` close, rounded top/bottom sheet corners (`rounded-t-3xl` / `rounded-b-3xl`), safe-area bottom padding, and a 44 px (`pointer-fine:size-9`) close button.
- [`card.tsx`](../../apps/web/src/components/ui/card.tsx): `Card` (`flat`, `raised`, `interactive`, and the quiet tints `warm`, `ink`, `ember`, `marigold`, `dusk` and `neem`, plus `asChild`), `CardHeader`, `CardTitle` (`asChild` for semantic headings), `CardDescription`, `CardContent` and `CardFooter`.
- [`badge.tsx`](../../apps/web/src/components/ui/badge.tsx): `Badge` (`neutral`, `brand`, `ember`, `marigold`, `dusk`, `neem`, `success`, `warning`, `destructive`, `outline` and `overlay` variants, plus `asChild`) for factual API-driven statuses and attributes.
- [`editorial-art.tsx`](../../apps/web/src/components/brand/editorial-art.tsx): `ListingPlaceholderArt`, the labelled stand-in when a PG has no photo yet.
- [`skeleton.tsx`](../../apps/web/src/components/ui/skeleton.tsx): `Skeleton` (`aria-hidden`, stops pulsing under `prefers-reduced-motion`).
- [`separator.tsx`](../../apps/web/src/components/ui/separator.tsx): `Separator` on Radix Separator (`decorative` by default, horizontal or vertical).
