# ADR 0023: The ops console: listings built from a phone, behind the API's rules

- Status: accepted
- Date: 2026-10-25
- Build step: 2.4 (ops console: listings)

## Context

Ops staff list PGs from the street, on a phone: they meet the owner, stand outside the building, take photos and fill in rooms and rents. Step 2.4 is the first place staff write catalog data, so it settles:
- how the web app edits what the API owns (ADR 0021's rules, the state machine, the paise);
- how a pin gets onto a building with a map behind the `MapProvider` interface (ADR 0006), before any map provider has been chosen;
- how photos go from the phone to storage (ADR 0022);
- what a change leaves behind for later readers (the audit log).

## Decision

1. **The API.** Everything is under `/v1/ops/*`, for ops and admins in a staff session (field agents are refused; their own screens come with verification).
   - **Owners are added by phone number** (`POST /v1/ops/owners`). The account is made if the owner has never signed in, the owner role is added, all in one transaction. The same phone twice is `409 OWNER_EXISTS`. Owners are found by exact phone or by part of a name.
   - **A listing starts as a draft** with the owner, the locality and the building. The answer lists any other listing whose exact pin is within 30 m (`possibleDuplicates`), likely the same building listed twice.
   - **Every change answers with the whole listing**, as `GET` would show it. A form never has to piece the result together.
   - **The listing says what the console may do with it.** `nextStatuses` gives the statuses the state machine allows from the current one, and `problems` gives what stops it being published. Each category carries `bedsPerRoom`. So the browser never keeps its own copy of a business rule.
   - **`PATCH` changes only the fields sent**, and the audit entry names exactly those. The console sends only what was edited, so the history means something. An untouched pin keeps its public display point, and a moved one gets a new one.
   - **History** comes from the audit log: the listing's own entries and its categories', rooms' and beds', newest first.
   - **Cross-module reads** (`identity.Accounts`, `geo.GeoLookup`, `media.MediaLookup`) run in the caller's transaction. Each read takes the same number of queries however many rooms a listing has.
2. **The pages** are `/ops/listings` (filter by status, search, cursor pages), `/ops/listings/new`, and `/ops/listings/{id}` (status, details, rooms and beds, amenities, photos and videos, history).
   - They are server components that read through the typed client. The proxy checks the session first, then each page checks for ops or admin, and the area is `noindex`.
   - **Forms** use React Hook Form and Zod, call the API from the browser with the CSRF token, then refresh the page's server components. The API's field errors show next to their fields. `LISTING_INVALID`, `LISTING_INCOMPLETE` and `MEDIA_NOT_ALLOWED` show the API's own detail, in English: the console is for staff.
   - **Choices are made on purpose.** Who it's for, meals, how exact the pin is, and a category's sharing start unchosen. Every enum's options come from a record keyed by every API value (`valuesOf`), so the compiler refuses a form that falls behind the API.
   - **Money:** the browser only turns typed rupees into integer paise, exactly, and shows the API's paise with `formatINR`. It works out no price: the API sums the charges (`monthlyChargesPaise`, `oneTimeChargesPaise`).
   - **Messages:** the console's forms format their own messages (file names, room labels), so `/ops` gets a `NextIntlClientProvider` with the `Ops` messages only (ADR 0011). Public pages still ship no message formatter.
3. **The pin picker.**
   - **Three ways to place it, all kept in step:** the phone's GPS ("Use my location", with its accuracy shown), typed coordinates, and the map (drag the pin, tap where it goes, or move it with the arrow keys).
   - **The map** comes from the `MapProvider` interface, which gains `PinPicker` next to step 3.5's `MapView`. Both Google's and MapLibre's SDKs can do a draggable pin.
   - **The first adapter is MapLibre GL 6** (BSD, free) with raster tiles:
     - It loads only with the pin picker (`next/dynamic`, no server rendering).
     - Its worker is emitted as a hashed static file, under both Turbopack and webpack (`setWorkerUrl`, as MapLibre's guide for Next.js says).
     - The CSP's `worker-src 'self'` covers the worker. The tiles' origin goes in `connect-src` and `img-src`, and only when tiles are set up.
     - Phone users scroll the page past the map with one finger (cooperative gestures), and the credits are underlined.
   - **Tiles are configuration.** `NEXT_PUBLIC_MAP_TILES_URL` and `NEXT_PUBLIC_MAP_TILES_ATTRIBUTION` set them, and a deployed site refuses tiles without their credit. With neither set:
     - local development uses OpenStreetMap's own tile servers, light use that their tile policy allows (the browser tests answer tile requests themselves);
     - anywhere else there is no map, and ops place the pin by GPS or coordinates.
   - **The production map provider (Google, or Ola's tiles) is the founders' choice**, a paid vendor (ADR 0006, CLAUDE.md). The interface lets their choice be an adapter and two settings.
   - **No made-up places.** A map with no pin opens on the chosen locality's verified centre (`GET /v1/localities`), or else all of NCR. NCR's box limits the map, as the API's check does.
4. **Photos and videos** go from the phone straight to storage with ADR 0022's presigned form. The console then waits for the worker, more slowly as time passes, for up to 5 minutes, and adds each ready file to the end of the listing's order. Changes to the order are queued, so uploads finishing together never undo each other. The first file is the cover, and each change saves the whole order.
5. **Tests.**
   - Unit tests cover the paise conversions, the details and category values, the API's field errors, the tile settings and the CSP's origins.
   - **A browser test** runs on a phone against the real API:
     - an ops account is made and its authenticator enrolled, as an operator would (`scripts/e2e-manage.sh`, the code worked out in the test);
     - then it signs in, adds an owner, places the pin by mocked GPS, adds a category with a charge, a room and its beds, amenities and a photo, and publishes;
     - axe checks the pages.
   - For that test, the e2e API now runs beside its worker, with its own buckets and the geo data loaded (`scripts/e2e-env.sh`).

## Consequences

- **Founders' decisions:**
  - the map provider and its key for production tiles (until then a deployed console has no map, only GPS and coordinates);
  - the tile provider's attribution text with it.
- **Step 3.5** adds `MapView` to the same interface and the provider the founders choose. The MapLibre adapter stays as the alternative ADR 0006 names.
- **Field agents' screens** (verification visits) and owner self-service reuse these forms with their own policies later.
- **The schema:** two pairs of API schemas shared a name, so the client got module-path names like `app__modules__...`. They are now `LatLng` and `ListingLocality`, and a test keeps every schema name plain.
