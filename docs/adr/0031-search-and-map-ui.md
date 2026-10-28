# ADR 0031: Search and its map: the URL holds the search, the server paints the first page, and the map's code loads only where the map shows

- Status: accepted
- Date: 2026-10-28
- Build step: 3.5 (search and map UI)

## Context

- **BUILD_PLAN 3.5** asks for:
  - a split view on a desktop, and the list first on a phone, with a map toggle and a draggable bottom sheet;
  - price pins with ranges, clustering, and "search as I move the map";
  - filters in the URL (nuqs), and cards and pins that light up together;
  - campus rings and metro stations, and the map locked to NCR;
  - a map behind the `MapProvider` interface, loaded lazily;
  - skeletons and empty states, and pins people can reach with a keyboard.
- It's done when a browser test goes filter → pan → select a pin → open the PG's page, on a phone and a desktop, and the map's code loads only on the map view.
- **ARCHITECTURE §10.3** describes the showcase:
  - debounce the map's moves by 300 ms and cancel stale requests;
  - a preview card for a selected pin;
  - the same results through the list for keyboard and screen reader users.
- **§16** puts search state in the URL, client calls in TanStack Query, and the map behind `MapView`.
- **The Google adapter.** BUILD_PLAN says "Google adapter first", but Google Maps Platform is a paid vendor, which the founders choose (CLAUDE.md). ADR 0023 already made MapLibre with configured raster tiles the first adapter.

## Decision

1. **The URL is the search.**
   - nuqs parsers (`src/lib/search/params.ts`) are the one definition, keyed by the API's own parameter names. The server page reads them with nuqs's loader and the browser with `useQueryStates`.
   - `searchQuery()` turns them into the API's query and drops anything a hand-edited URL got wrong (a bad slug, month or amount, more than 20 amenities, a radius not offered), so the page still shows something.
   - It searches one place: a map area first, then a campus, then a locality. Sorting by distance needs a campus.
   - Updates are shallow: no server render per change. They replace the history entry, except the phone's list/map toggle, which pushes one, so Back returns to the list.
2. **The first page comes from the server; the browser does the rest.**
   - `/search` renders the first page of results for its URL, from Next's data cache (30 seconds, as the API's `Cache-Control` says; tag `listings`). A shared link shows its results before any script runs.
   - After that, the browser calls the API through TanStack Query, with keys `["search", query]`, `["map-pins", query]` and `["listing", slug]`.
   - Each call gets the query's `AbortSignal`, so a request the person has moved on from is cancelled.
   - Results stay on screen, dimmed and `aria-busy`, while new ones load.
   - A 4xx isn't retried, and a `422 SEARCH_INVALID` shows the API's reason.
   - The providers wrap `/search` only, so other pages ship neither library.
3. **`MapView` joins the `MapProvider` interface**, with a MapLibre adapter (ADR 0023), and no Google adapter until the founders approve one. The interface carries:
   - the pins, which are selected or hovered, and a bounds callback that says whether the person moved the map;
   - the campuses, the chosen campus, and the stations;
   - where to look first, and a target place the map goes to when its key changes.
4. **Pins are buttons.**
   - Each pin is an HTML button, named with the month's full price range, who the PG is for, and whether it's verified.
   - Clustering is MapLibre's own (48 px, until zoom 15). A cluster's button says how many PGs it holds and the lowest price among them, and pressing it zooms in.
   - Buttons outside the visible area are `inert`: focusing one would scroll the map's container.
5. **Overlays.**
   - Campuses are dots, as many lie within a kilometre of each other. The chosen campus has its name and its 1 km and 2 km rings.
   - Metro stations are dots too. The overlays credit OpenStreetMap, as ADR 0020 requires.
   - The map is locked to NCR's box, at zoom 9 to 18, without rotation, with cooperative gestures.
   - **No locality outline:** localities are centres only in the API, so the map shows 1.5 km around a locality's centre. Outlines need boundary data first.
6. **Search as I move the map.**
   - It's on to begin with. A move the person made sets `bbox` (five decimal places) and drops the campus or locality, 300 ms after the map rests.
   - A person's move is a drag, the wheel, the keys, the zoom buttons or a cluster's button. MapLibre passes the original event on for all of them, and the cluster buttons pass theirs.
   - The page's own moves, loading or going to a chosen place, never count.
   - With it off, a "Search this area" button appears after a move.
7. **Phone and desktop.**
   - **From 1024 px:** the list sits beside a full-height map that stays in view.
   - **Below 1024 px:** the list comes first, with a "Show the map" button.
     - The map then fills the screen under the header, with the list in a bottom sheet: a peek, half the screen or nearly all of it.
     - The sheet is dragged by its handle, or the handle is tapped to step through the same heights, so no one has to drag (WCAG 2.2 2.5.7). Tabbing into a peeking list opens it.
   - **The map's code loads only where the map shows:** MapLibre, its styles and its worker are a chunk of their own.
     - On the desktop's split view, it loads after hydration.
     - On a phone, it loads when the map is opened.
     - The browser test checks that a phone's list view fetches none of it.
8. **Cards and pins together.**
   - Hovering or focusing a card lights its pin, and the other way round.
   - Selecting a pin opens a preview over the map:
     - the month's prices come from the pin;
     - the name and photo come from the results when they hold the PG, or else from its public data.
   - Focus moves to the preview, and Escape returns it to the pin.
9. **Filters.**
   - Native selects and checkboxes sit in a sheet, from the left on a desktop and from the bottom on a phone. Each applies as it changes, and nothing is pre-ticked.
   - Typed text waits 400 ms, or applies at once on Enter.
   - The budget steps are thresholds in rupees, only formatted with `formatINR` (CLAUDE.md rule 12).
   - The sheet's code loads the first time it opens, as dialogs should (frontend rules). The pin preview and the phone's list sheet load with the map.
10. **Speed.**
    - A page holds 12 results: a phone shows four or five at once, and "Show more PGs" brings the next 12.
    - The first card's photo is the page's largest paint, so it loads at once with high priority; the rest load lazily.
    - **`radix-ui` is imported member by member** (`optimizePackageImports`). Its one entry point re-exports every primitive, and webpack had kept all of them (about 60 KB gzipped) on every page for the two the site uses.
      - Client JavaScript fell from 228 KB to 152 KB gzipped on the home page, and from 227 KB to 153 KB on a PG page.
      - Search ships 197 KB, within ARCHITECTURE §16's 200 KB.
    - **`make lighthouse-search`** audits search's list on Lighthouse's mobile profile against the browser tests' API, and fails below 85. It scored 89 for performance (runs of 89, 86, 83, 91 and 89) and 100 for accessibility, best practices and SEO.
11. **Sample PGs one run at a time.** Browser-test workers start `catalog samples` together, so a run now holds an advisory lock while it makes them. A second run waits, then finds them there.

## Consequences

- `/search` is one canonical URL. Filtered searches aren't separate pages for search engines; landing pages per campus and locality are step 3.6.
- The pins' prices are the month's base rents (ADR 0027) until dynamic pricing (phase 4).
- **Search formats its messages in the browser,** so it ships next-intl's ICU parser (about 12 KB gzipped).
  - next-intl's experimental precompiled messages would drop the parser.
  - First, `t.raw` has to go from the three files that use it, and the global error page has to stop importing the whole message file, which would otherwise ship compiled on every page.
- **Founders' decisions:**
  - Whether to add a Google Maps adapter. It's a paid vendor, and the interface is ready for it.
  - Which tile provider serves production with MapLibre. Until one is set up, a deployed site shows the list without a map (ADR 0023).
