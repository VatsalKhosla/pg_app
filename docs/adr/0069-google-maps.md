# ADR 0069: Google Maps behind the map interface, with MapLibre as the fallback, and maps that move smoothly

- Status: accepted
- Date: 2026-11-15

## Context

- The founders asked for Google Maps, and for maps that are "actually smooth and easy to use". They will create the Google key later, so the site has to keep working on today's free map (MapLibre with OpenStreetMap's tiles) until it's set.
- ADR 0006 put every map behind the `MapProvider` interface, with Google's adapter to come once the founders chose a paid vendor (ADR 0023, 0031). Only MapLibre's existed.
- What wasn't easy: on a desktop the wheel zoomed only with Ctrl or ⌘ held, and on a phone the full-screen search map wouldn't move with one finger. Google's own fitBounds jumps rather than glides when a place is far away.
- The page's JavaScript budget is strict (about 200 KB gzipped on a PG page), and the Content Security Policy runs scripts by nonce only, with 'strict-dynamic'.

## Decision

1. **Which map.** Google's is used only when `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` and `NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID` are both set (`src/config/env.ts`). Otherwise every map is MapLibre's, exactly as before. A value that can't be a key or an ID stops the build.
   - If Google's script can't load, or Google refuses the key later (`gm_authFailure`: wrong site, API off, no billing), every map goes back to MapLibre's tiles for the rest of the visit (`choice.ts`), or says it couldn't load where there are none.
   - Only the chosen adapter's chunk is fetched, and only where a map shows, as before. The pages' first JavaScript gains only the choice itself.
2. **The Google adapter** (`components/map/google/`) does what MapLibre's does, behind the same props.
   - **Search map.** Pins and clusters are Google's clickable HTML markers (`AdvancedMarkerElement`, which needs the map ID), with the same names, `data-pin-id`, `data-state` and `aria-pressed` as MapLibre's buttons. Tab reaches the first and the arrow keys the rest in view, which is Google's supported way: a button inside a marker works today, but Google says focusable children aren't supported.
   - **Clusters** come from supercluster with MapLibre's settings (48 px, until its zoom 15), so both maps group the same pins alike. A cluster shows its count and lowest price, and opens with a glide.
   - **Overlays.** Campus and station dots, the chosen campus's rings and label, and OpenStreetMap's credit for them (ADR 0020), beside Google's own.
   - **The rest.** `onBoundsChange` with `byPerson`, told from the person's hand on the map, since Google's events don't say who moved it. Fitting to `initial` and `target`, and the floating list's `insetLeft`. The desktop's tilt and heading on the vector map; where Google falls back to raster, the map stays flat and the button hides.
   - **PG page:** the area circle. **Pin picker:** Google's draggable pin, a click or tap, and the arrow keys (a pixel, ten with Shift).
   - Its own zoom buttons, in the page's words and below the search page's header, as Google's control can't be.
   - Zoom in the interface stays MapLibre's (512 px tiles), which the search API takes. Google's runs one higher, and the adapter converts.
   - The map is drawn in the page's light or dark, with India's official boundaries (`region=IN`).
3. **Smooth and easy, on both maps** (`gestures.ts`):
   - **With a mouse or trackpad,** the wheel zooms straight away.
   - **On a touch screen,** the PG page's map and the pin picker leave one finger to the page and move with two, as before. The search map fills its screen, with no page to scroll past it, so one finger moves it.
   - **Moves glide.** Google's adapter animates the camera itself, frame by frame: flights to a place along MapLibre's flyTo path, eased zooms and cluster opens. A hand on the map stops a glide. Anyone who asks for less motion gets every move at once, on both maps.
4. **The CSP** opens to Google only when both settings are set (`src/proxy.ts`), as Google's CSP guide lists:
   - images and connections from `*.googleapis.com`, `*.gstatic.com` and `*.google.com` (plus `*.googleusercontent.com` for images, and the `data:` and `blob:` URLs the vector map reads);
   - Google Fonts for the map's font, and `*.google.com` frames;
   - `'wasm-unsafe-eval'`, which Google's code tries behind a feature check.
   - **Scripts need nothing new.** The policy already has `'strict-dynamic'`. Google's loader gives its script the page's nonce, and `'strict-dynamic'` trusts the scripts and blob scripts that script adds. Google's sample policy also has `'unsafe-eval'`; its code uses eval only in an old JSON fallback, so the policy leaves it out.
   - Probed in Chromium on 2026-11-14 against Google's live script with this policy: no violations.
5. **Dependencies,** pinned exactly:
   - `@googlemaps/js-api-loader` 2.1.3, Google's official loader;
   - `supercluster` 9.1.0, the clustering MapLibre runs inside. `@googlemaps/markerclusterer` wraps the same library, but redraws every cluster marker on each change (losing focus), zooms with fitBounds and keeps no lowest price;
   - `@types/google.maps` 3.66.10, for development only.
6. **Build.** The staging image is built in CI and Render runs it as it is, so the two values come from the repository's Actions variables into the image (`Dockerfile`, `make web-image`, the Deploy staging job). Setting them on Render's service alone would change nothing. The founders' steps are in `docs/runbooks/staging.md`.

## Consequences

- With no key, nothing changes for visitors but the gestures and motion above. The browser tests run on MapLibre.
- **Checked in a browser:** search on Google's map (names, a click, a drag searching the new area, a cluster opening, zoom buttons, no CSP violations), and the fall back to MapLibre when Google refuses the key.
  - Headless Chromium here gets Google's raster fallback, so the vector map's tilt and the glides on it wait for a real key on a real device.
  - The pin picker and the PG page's map on Google weren't driven in a browser.
- **Billing.** Each map shown is a map load in Google's billing: opening the phone's map view again loads it again. The founders' budget alerts (ADR 0006) watch the cost.
- **Map loads that fail** (a key restricted to the wrong address, say) show MapLibre's map rather than Google's error, so a mistake there is quiet. The browser console says why.
- If Google ever enforces `'unsafe-eval'` or another origin, the violation reaches Sentry first. That, and the vector map on real devices, is what to check once the key is live.
