# Design system

This document records the tokens, typography, motion and UI primitives built in step 1 of the [UI refresh](ui-refresh.md), drawing on Airbnb India (airy surfaces, warm geometric display headings, soft layered elevation, pill-shaped search and filter chips, whole-card interactive targets) and Expedia India (high-contrast control borders, structured status badges, scannable price and booking cards).

## 1. Colour and contrast

Brand colours live only in [`apps/web/src/config/brand.ts`](../../apps/web/src/config/brand.ts) and reach CSS through `brandStyle` (`--brand-*` custom properties on `<html>`). Semantic tokens and soft brand mixes live in [`apps/web/src/app/globals.css`](../../apps/web/src/app/globals.css).

Every text pair meets at least 4.5:1 contrast, and control outlines (`--input`) and focus rings (`--ring`) meet at least 3:1 (WCAG 2.2 AA) in both light and dark mode:

| Token pair | Light | Ratio | Dark | Ratio |
| --- | --- | --- | --- | --- |
| `--foreground` on `--background` | `#121718` on `#ffffff` | 18.1:1 | `#f2f6f6` on `#0c1012` | 17.5:1 |
| `--foreground` on `--surface` | `#121718` on `#f6f9f9` | 17.1:1 | `#f2f6f6` on `#111618` | 16.9:1 |
| `--card-foreground` on `--card` | `#121718` on `#ffffff` | 18.1:1 | `#f2f6f6` on `#14191b` | 16.2:1 |
| `--muted-foreground` on `--background` | `#566061` on `#ffffff` | 6.5:1 | `#a6b0b2` on `#0c1012` | 8.6:1 |
| `--muted-foreground` on `--muted` | `#566061` on `#f2f6f6` | 6.0:1 | `#a6b0b2` on `#1e2426` | 7.1:1 |
| `--primary-foreground` on `--primary` | `#ffffff` on `#0e6b74` | 6.2:1 | `#062a2e` on `#5ec4cc` | 7.4:1 |
| `--primary` on `--background` | `#0e6b74` on `#ffffff` | 6.2:1 | `#5ec4cc` on `#0c1012` | 9.3:1 |
| `--primary-soft-foreground` on `--primary-soft` | `#074e54` on `#eaf1f2` | 8.3:1 | `#94d6db` on `#19282c` | 9.4:1 |
| `--destructive-foreground` on `--destructive` | `#ffffff` on `#c51e21` | 5.9:1 | `#0c1012` on `#f96f70` | 6.9:1 |
| `--destructive` on `--background` | `#c51e21` on `#ffffff` | 5.9:1 | `#f96f70` on `#0c1012` | 6.9:1 |
| `--destructive-soft-foreground` on `--destructive-soft` | `#b7191c` on `#ffeeee` | 5.9:1 | `#fda19e` on `#3f1919` | 7.9:1 |
| `--success-soft-foreground` on `--success-soft` | `#036639` on `#e0f9e8` | 6.4:1 | `#80dba2` on `#122d1d` | 8.9:1 |
| `--warning-soft-foreground` on `--warning-soft` | `#864900` on `#fff2ce` | 6.3:1 | `#efc876` on `#37250e` | 9.3:1 |
| `--input` (control border) on `--background` | `#848e90` on `#ffffff` | 3.3:1 | `rgb(255 255 255 / 36%)` on `#0c1012` | 3.3:1 |
| `--ring` (focus indicator, even at 50%) on `--background` | `#121718` on `#ffffff` | 18.1:1 (3.4:1 at 50%) | `#f2f6f6` on `#0c1012` | 17.5:1 (5.0:1 at 50%) |

## 2. Typography

Loaded via `next/font/google` in [`apps/web/src/app/layout.tsx`](../../apps/web/src/app/layout.tsx) (self-hosted at build time, `display: "swap"`, Latin preloaded):

- **Sans (`--font-sans`):** `Inter` (variable). Used for body copy, form controls, tables and ₹ figures.
- **Display (`--font-display`):** `Plus Jakarta Sans` (variable). Applied automatically to `h1`, `h2` and `h3` in the base layer with `text-wrap: balance`, and available via `font-display`.

Fluid display scale in `@theme inline`:

- `text-display`: `clamp(2.25rem, 1.65rem + 3vw, 4rem)`, line-height `1.05`, tracking `-0.03em`
- `text-title-1`: `clamp(1.75rem, 1.5rem + 1.25vw, 2.5rem)`, line-height `1.12`, tracking `-0.025em`
- `text-title-2`: `clamp(1.375rem, 1.25rem + 0.7vw, 1.875rem)`, line-height `1.2`, tracking `-0.02em`
- `text-title-3`: `1.25rem`, line-height `1.3`, tracking `-0.015em`
- `text-eyebrow`: `0.75rem`, line-height `1.33`, tracking `0.08em`

## 3. Space, radius and elevation

- **Layout rhythm:** `px-gutter` (`clamp(1rem, 0.6rem + 2vw, 2.5rem)`), `py-section` (`clamp(3rem, 2rem + 5vw, 6.5rem)`), `max-w-page` (`78rem`) and `max-w-prose` (`42rem`).
- **Radius scale:** controls use `rounded-lg` (`0.75rem`), cards use `rounded-xl` (`1rem`), larger panels use `rounded-2xl` (`1.25rem`) and sheets/hero surfaces use `rounded-3xl` (`1.75rem`).
- **Layered shadows:** `--shadow-2xs` through `--shadow-xl` combine a tight contact shadow and a soft ambient shadow tinted with `--shadow-tint` (`16 24 28` in light mode, `0 0 0` at 3× strength in dark mode).

## 4. Motion

- **Curves:** `ease-standard` (`cubic-bezier(0.2, 0, 0, 1)`), `ease-emphasized` (`cubic-bezier(0.16, 1, 0.3, 1)`) for entrances, and `ease-exit` (`cubic-bezier(0.3, 0, 0.8, 0.15)`) for exits.
- **Durations:** `--duration-fast` (`120ms`), `--duration-base` (`200ms`), `--duration-slow` (`320ms`), `--duration-slower` (`480ms`).
- **Keyframe utilities:** `animate-rise` and `animate-fade`.
- **Reduced motion (WCAG 2.3.3):** `@media (prefers-reduced-motion: reduce)` disables smooth scrolling, collapses animation and transition durations/delays to `0.01ms` / `0s`, and turns off view-transition animations.

## 5. Primitives (`apps/web/src/components/ui`)

- [`button.tsx`](../../apps/web/src/components/ui/button.tsx): `default`, `soft`, `destructive`, `outline`, `secondary`, `ghost` and `link` variants; `default`, `sm`, `lg`, `icon`, `icon-sm` and `icon-lg` sizes; `default` and `pill` shapes. Touch targets are 44 px tall (`h-11`, `size-11`) on coarse pointers and tighten to 40 px (`pointer-fine:h-10`) under a mouse so owner and ops screens stay compact. Every size including `sm` and `link` stays at or above 24×24 px (WCAG 2.5.8).
- [`input.tsx`](../../apps/web/src/components/ui/input.tsx) & [`fields.tsx`](../../apps/web/src/components/ui/fields.tsx): shared `controlClasses` with a 3:1 `--input` border, 16 px text on phones (preventing iOS zoom on focus), 44 px touch height (`pointer-fine:h-10`), and a 2 px focus ring (`border-ring` + `ring-1 ring-ring`). `Choices` highlights the checked radio card with `border-primary`, `bg-primary-soft` and `ring-1 ring-primary` so selection never relies on colour alone (WCAG 1.4.1).
- [`sheet.tsx`](../../apps/web/src/components/ui/sheet.tsx): Radix Dialog drawer with `ease-emphasized` entrance, `ease-exit` close, rounded top/bottom sheet corners (`rounded-t-3xl` / `rounded-b-3xl`), safe-area bottom padding, and a 44 px (`pointer-fine:size-9`) close button.
- [`card.tsx`](../../apps/web/src/components/ui/card.tsx): `Card` (`flat`, `raised`, `interactive` variants, plus `asChild`), `CardHeader`, `CardTitle` (`asChild` for semantic headings), `CardDescription`, `CardContent` and `CardFooter`.
- [`badge.tsx`](../../apps/web/src/components/ui/badge.tsx): `Badge` (`neutral`, `brand`, `success`, `warning`, `destructive`, `outline` and `overlay` variants, plus `asChild`) for factual API-driven statuses and attributes.
- [`skeleton.tsx`](../../apps/web/src/components/ui/skeleton.tsx): `Skeleton` (`aria-hidden`, stops pulsing under `prefers-reduced-motion`).
- [`separator.tsx`](../../apps/web/src/components/ui/separator.tsx): `Separator` on Radix Separator (`decorative` by default, horizontal or vertical).
