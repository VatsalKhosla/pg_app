# Frontend v2: inspiration, organised

Status: palette not yet chosen (2026-11-08). The founders' design page shows the same board, with the palette previews: https://claude.ai/artifact/BQHSAzaGFKzHXhcpZBwo5c (private to the founders' account).

This file records what we took from each reference and what we left. "Leave" is usually the honesty rule (CLAUDE.md rule 7, `ui-refresh.md`): no invented numbers, ratings, urgency or fees. The sketches on the design page are layout diagrams, not copies.

## The board
Each source has labels for what it teaches: layout, type, colour, components, motion or imagery.

### LeonHome (luxury real estate; founders' attachment)
- Labels: type, layout, colour, components.
- **Take:**
  - a giant serif headline as the hero's anchor;
  - glass stat cards floating over the hero;
  - a quiet neutral base with one warm accent.
- **Leave:**
  - big counters with invented numbers (ours come from the API, or don't show);
  - a tone of exclusivity (students and parents need warmth and clarity).

### "Discover Journeys" (travel landing page; founders' attachment)
- Labels: layout, components, motion, imagery.
- **Take:**
  - a search capsule floating over the hero's bottom edge;
  - an oversized headline with one accent word;
  - a golden-hour mood, which we draw as illustration rather than use a photo.
- **Leave:**
  - traveller counts and star ratings we can't prove;
  - a video hero (phones and reduced-motion users get a still).

### Reome (rentals browse page; founders' attachment)
- Labels: layout, components.
- **Take:**
  - search right in the hero;
  - a calm card grid where the price is easy to find;
  - filter chips one tap away.
- **Leave:** a lone headline price. We show the full monthly price, deposit and charges together.

### Airbnb India (airbnb.co.in; founders' brief)
- Labels: components, layout, motion.
- **Take:**
  - a category rail with icons;
  - swipeable photos on each card;
  - map and list side by side, with price pills;
  - a reservation card that stays in view;
  - a 1+4 photo mosaic;
  - a compact search bar once the page scrolls.
- **Leave:**
  - "rare find" style badges unless real inventory says so;
  - service-fee lines (students never pay a fee).

### Expedia India (expedia.co.in; founders' brief)
- Labels: components, layout.
- **Take:**
  - refund status as a clear label on every result, with a filter for it (ours: "Refundable token");
  - a price summary that says what is paid now and what comes later (ours: the token now, counted toward the first month's rent, with amounts from the API).
- **Leave:**
  - member-only prices, and "only a few left" banners unless inventory says so;
  - review scores we don't have.

### Delhi itself (our own source)
- Labels: colour, imagery, motion.
- **Take:**
  - Metro wayfinding: line colours, station dots, "your stop";
  - marigold, jamun, sodium-lit evenings;
  - rooftop water tanks and To-Let boards as illustration motifs.
- **Leave:** real PG names or landmarks drawn as if they were near a listing.

### Toolbox: 21st.dev
- Its MIT-licensed search-hero and floating-header components are starting points only.
- Each is rebuilt on our tokens, labels and translations.
- Nothing comes in without a clear licence, or if it loads fonts or scripts from a CDN.

## Patterns, and where they land
| Pattern | Page |
|---|---|
| Hero with a floating search capsule and an illustrated Delhi street scene with depth | Home |
| Stat tiles with real numbers only (a missing number shows nothing) | Home |
| Budget explorer: a budget slider lighting up matching PGs on a mini map | Home |
| Stay simulator: search to move-in, with every figure from the live policy | Home, token page, booking |
| Map and list with price pills, swipeable card photos, a sticky compact search bar, a 3D map tilt on desktop | Search |
| The card's photo grows into the PG page's hero (view transition) | Search, then the PG page |
| 1+4 photo mosaic; a reservation card on desktop and a bottom bar on phones | PG page |
| Room-type viewer: the real bed layout as a labelled 3D-style illustration | PG page |
| Commute view: a straight line to the campus and the nearest metro, with the API's distance | PG page, map preview |

## Palettes (founders to choose)
Each palette was checked for WCAG AA, in light and dark:
- text 4.5:1 or more;
- control borders and focus rings 3:1 or more.

| Option | Name | Light: primary / accent / ink / paper | Idea |
|---|---|---|---|
| A | Golden hour | `#1e2b45` / `#f0a93b` / `#161a22` / `#fbf8f2` | Ink and marigold on ivory: the references' sunset warmth, with an ink parents trust |
| B | Metro | `#1546a8` / `#ffc72c` / `#0f1729` / `#f7f9fc` | Line blue and Yellow Line yellow: Delhi Metro's wayfinding, which pairs with the commute view |
| C | Jamun | `#5b2a86` / `#ffb547` / `#1d1426` / `#faf8fc` | Jamun violet and mango: rich, youthful and unlike other rental sites |

## Type
- **Fraunces** (SIL Open Font License, through `next/font`, not preloaded) sets display headlines from 24 px up.
- **Inter** stays for text and figures; its even-width digits keep rents lined up.
- Plus Jakarta Sans is retired, so the site loads one font fewer.
