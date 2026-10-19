# ADR 0006: The map provider sits behind an interface

- Status: accepted
- Date: 2026-10-19 (recorded in step 0.8; decided in the founders' planning, ARCHITECTURE §10 and §16)
- Build step: 0.8 (ADRs and runbook stubs)

## Context

The map is the showcase feature: price pins, clusters, campus rings and metro overlays across Delhi NCR. Map providers' India pricing, quotas and terms keep changing.
- **Google Maps Platform** has the strongest India data.
- **MapLibre GL with Ola Maps tiles** is a cheaper alternative.

Both must show India's official boundaries. Code written straight against one vendor's SDK would make switching a rewrite, and that SDK is heavy JavaScript the page budget can't afford on every page.

## Decision

1. **Web code depends only on a `MapProvider` interface:** a `<MapView pins onBoundsChange onPinSelect selectedId overlays bounds />` component, plus the types it takes. Vendor SDKs are imported only inside adapters.
2. **Two adapters:**
   - `GoogleMapView` (default): Google Maps JavaScript API through `@vis.gl/react-google-maps`.
   - `MapLibreMapView` (alternative): MapLibre GL with Ola Maps tiles, checked against their docs when it is built.
   - The small map on PG pages uses Google's free Maps Embed API.
3. **The adapter loads on demand.** It is dynamically imported only when the map view opens, never in the initial bundle.
4. **The API stays provider-neutral.** `GET /v1/map/pins` returns compact pins (`display_location`, prices, badges), and clustering happens on the client.
   - Exact locations never reach a map before a visit is scheduled or a booking confirmed. `display_location` is a stored offset of 80–150 m.
   - Server-side geocoding, if ever needed, goes behind a port with a test adapter, like every other external service.
5. **Keys and costs:**
   - Browser keys are restricted by HTTP referrer and API.
   - Provider consoles carry budget alerts.
   - Prices and quotas are checked again before launch.

## Consequences

- Switching providers is an adapter and configuration change, not a rewrite.
- The interface offers only what both providers can do. A provider-only feature needs an interface change on purpose.
- Each adapter needs its own tests, and the map must stay usable from the keyboard: the result list mirrors the pins, and the pins are focusable.
- Choosing a paid tier or signing up with a provider is the founders' decision (CLAUDE.md).
