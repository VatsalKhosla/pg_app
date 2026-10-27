# ADR 0029: Map pins: compact pins at display points, 2,000 at most, cached in Redis for a minute by an area snapped to the zoom, with ETags

- Status: accepted
- Date: 2026-10-27
- Build step: 3.3 (map pins API)

## Context

- **ARCHITECTURE §10.2** specifies `GET /v1/map/pins`: a map area, the zoom and search's filters give up to 2,000 compact pins with price ranges, at display points. Answers are cached in Redis by rounded area, zoom and a hash of the filters for 60 seconds, with ETags, and the client clusters the pins.
- **BUILD_PLAN 3.3** is done when a pan across NCR returns the right pins, and repeated calls are answered from the cache.
- The map asks again after every pan, so most of its requests repeat recent ones.

## Decision

1. **Pins come from search's read model and price summaries** (ADR 0028), with the same filters as search. Since the area is the place, there is no campus or locality, and no sort, cursor or limit.
   - A pin is: `{id, slug, lat, lng, minRentPaise, maxRentPaise, genderPolicy, verified, bedsFree}`, at the display point (ADR 0021).
   - The privacy sweep (ADR 0026) finds its listing among the pins too.
2. **At most 2,000 pins**, in a stable order. `truncated` says more matched, so the map can ask the person to zoom in.
3. **The area is snapped outwards** to a grid a quarter of a map tile wide at that zoom: 360° / 2^(zoom + 2) a cell.
   - A small pan asks for the same area again, so it finds the answer already cached.
   - Pins just outside the view come too, and the map clusters them with the rest.
4. **The cache.**
   - The key is the snapped area, the zoom, the month, whether only verified listings show, and a hash of the other filters.
   - Each answer is kept for 60 seconds as the exact JSON the API sends, with its ETag (part of the body's SHA-256).
   - A repeated request touches neither the database nor the serializer.
   - The cache is only a convenience: when Redis is down, pins come straight from the database.
   - There is no invalidation on events. A listing's change reaches the map within a minute, which suits a map.
5. **HTTP.**
   - Each answer carries `ETag` and `Cache-Control: public, max-age=60`.
   - `If-None-Match` with the current ETag, or `*`, gets `304 Not Modified` with no body.
   - Limited to 1,200 requests per 10 minutes per IP, and let through if Redis is down.
6. **Validation.**
   - The area and the zoom (5 to 20) are required, and unknown parameters are refused (422 `VALIDATION_ERROR`).
   - An area outside NCR, or a month without prices, is `422 SEARCH_INVALID`.

## Consequences

- The map UI (3.5) clusters on the client and shows `truncated` as a hint to zoom in.
- A listing's change, or a price summary's, reaches the map within a minute (the time-to-live), plus the seconds the refresh job takes. If that's ever too slow, bumping a generation number in each cache key on catalog events would make it immediate.
