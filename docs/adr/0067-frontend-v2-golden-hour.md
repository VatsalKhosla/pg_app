# ADR 0067: Frontend v2: Golden hour, an evening scene in CSS and SVG, and simulators that show only the live policy

- Status: accepted
- Date: 2026-11-08

## Context

The founders asked for a far more ambitious frontend than the UI refresh delivered, with real-data simulators, cinematic motion and 3D scenes. It still had to meet the honesty, accessibility, security and speed rules. They chose the Golden hour palette (ink, marigold, ivory), allowed 21st.dev as the only paid tool, and paused Antigravity. `docs/design/inspiration.md` records the references, and `apps/web/DESIGN.md` the visual world.

## Decision

1. **Scenes are server-drawn SVG, and motion is CSS.** The home page's evening is layers of inline SVG from seeded geometry. The sunset runs on scroll-driven animations. Everything that moves is a whole layer moved by `transform`, `translate` or `opacity`, so the compositor runs it. It adds no libraries and no WebGL, and three.js stays out. Under reduced motion it is a still picture.
2. **Simulators show only what the API says.** The stay simulator takes every figure from `getPolicies()` and reuses wording the founders had already approved. The budget explorer lights real pins from `/v1/map/pins`. The booking page's token track reads the booking's status. None of them computes money.
3. **The room viewer is a labelled illustration** drawn from each room type's own fields, never a picture of the room.
4. **Fonts are budgeted.** Eczar is loaded at one static weight (15 KB, against 86 KB or so for the variable file). A 2 KB subset holds the rupee sign, which otherwise cost Inter's whole 85 KB Latin Extended file.
5. **First-load JavaScript stays small.** What every page loads styles plain buttons from `button-variants.ts`, without `tailwind-merge` or Slot. Suspense boundaries split hydration, and the budget explorer loads as it nears the screen.
6. **Working tools stay working tools.** Owner, ops, field and admin screens keep the tokens, with Inter headings.

## Results

Lighthouse on a phone, median of three local runs, against the budgets of ADR 0066:

| Page | Before | After | Budget |
|---|---|---|---|
| Home | 84 (first v2 build) | 90 | 90 |
| A PG's page | 88 | 90 | 85 |
| Search | 81 | 87 | 85 |

## Consequences

- Search's audit stays report-only in CI until it has held 85 there. Then the `continue-on-error` line goes (ADR 0066).
- Search cards have one photo because the API returns one cover. A swipeable card needs that API to return more.
- The search map has a desktop tilt on its existing tiles. Building heights need vector tiles, which is the founders' map-provider choice.
- The 21st.dev connection is optional and waits on the founders' key. No component from it is in the code.
