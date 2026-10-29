# Reviewed changes to the API contract

`make api-breaking` (and CI's API contract job) fails on any change to the API schema that could break a client: a removed field, a narrowed type, a new value a client may not expect. Sometimes such a change is meant, and safe. A field may be renamed with the same shape, or an enum may gain a value that the only client, the web app, is regenerated for in the same commit.

Such a change is recorded here, in the commit that makes it, with its date and why it is safe. Each line names the method and path (or `components`) and oasdiff's description of the change, as `oasdiff breaking --format singleline` prints it. oasdiff then ignores exactly that change (its `--err-ignore` file). Nothing else is ignored.

Any public client outside this repository would need a new API version instead, never a line here.

- 2026-10-25 PATCH /v1/ops/properties/{property_id} removed `#/components/schemas/Location-Input` from the `location` request property `anyOf` list. The schema was renamed LatLng with the same shape (ADR 0023).
- 2026-10-26 POST /v1/media added the new `verification_photo` enum value to the `media/purpose` response property for the response status `201`. This is field agents' private evidence (ADR 0024).
- 2026-10-26 GET /v1/media/{media_id} added the new `verification_photo` enum value to the `purpose` response property for the response status `200`. Same change (ADR 0024).
- 2026-10-26 POST /v1/media/{media_id}/uploaded added the new `verification_photo` enum value to the `purpose` response property for the response status `202`. Same change (ADR 0024).
- 2026-10-30 GET /v1/quotes/{quote_id} added `#/components/schemas/MonthlyCharge, #/components/schemas/MeteredCharge, #/components/schemas/OneTimeCharge` to the `charges/items/` response property `oneOf` list for the response status `200`. A quote's charges took the catalog's own shape, so the PG page reads both alike; the web app, the only client, changed in the same commit, and quotes weren't live (ADR 0040). Recorded after CI flagged it.
- 2026-10-30 POST /v1/quotes added `#/components/schemas/MonthlyCharge, #/components/schemas/MeteredCharge, #/components/schemas/OneTimeCharge` to the `charges/items/` response property `oneOf` list for the response status `201`. Same change (ADR 0040).
