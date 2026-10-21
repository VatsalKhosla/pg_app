# ADR 0021: The catalog: owners, listings, room categories, rooms and beds

- Status: accepted
- Date: 2026-10-21
- Build step: 2.2 (catalog schema)

## Context

Everything that follows sells what the catalog holds:
- search and the map (Phase 3);
- the pricing engine (Phase 4);
- bookings and their inventory allocations (Phase 5).

The data model is in ARCHITECTURE §6. This step fills in what that leaves open:
- how the money columns are kept honest;
- how a listing's life is modelled;
- how the exact location stays private;
- what a room category's mandatory charges look like;
- how the catalog reaches the geo module without touching its tables.

## Decision

1. **A `catalog` module** owns `owners`, `properties`, `room_categories`, `rooms`, `beds`, `amenities` and `property_amenities`.
   - **Public ids:** owners, properties, room categories, rooms and beds have UUIDv7 public ids, since ops screens address all of them. Amenities are known by slug.
   - **No routes yet.** The ops console (step 2.4) puts screens on the service, and the public pages (Phase 3) read through search.
2. **Money is integer paise, checked twice.**
   - **The domain** (`domain/rooms.py`) refuses:
     - a base rent of zero or less;
     - an owner's minimum or maximum that leaves the base rent outside it;
     - a negative deposit.

     It reports every problem at once (`LISTING_INVALID`, 422).
   - **The database** repeats each rule as a named CHECK, so no path round the service can store a broken rent.
   - **Why the base rent must lie in the owner's range:** it is the price when no rule applies, and the placement fee is worked out on it (CLAUDE.md rules 2 and 6). A base rent outside the range would be clamped by every quote.
3. **Mandatory charges are typed**, in paise, in a JSON array:
   - **monthly:** a fixed amount each month;
   - **metered:** a rate per unit plus the owner's monthly estimate, so the full monthly cost can be shown (CLAUDE.md rule 7);
   - **one-time:** an amount at move-in.

   Each has a kind, from electricity to registration, and a label. Labels are unique per kind, amounts are positive, and there are at most 12. The database checks that the column is an array.
4. **A listing's life** (`domain/listing.py`):
   - **Transitions:** draft → published ⇄ paused; any → delisted; delisted → draft (to list again).
   - **Publishing** needs at least one active room category with an active bed (`LISTING_INCOMPLETE`, 409). Step 2.5 adds the verification gate.
   - **The first publication** sets `published_at`, and later ones keep it ("newest" sorts by first listing).
   - **Other moves** answer `INVALID_TRANSITION`.
5. **Rooms hold no more beds than their occupancy**: a double room has two (`ROOM_FULL`, 409).
   - **The race:** the room row is locked while a bed is added, so two at once can't both take the last place.
   - **Labels** are unique per category (rooms) and per room (beds), in the domain and as unique constraints (`LABEL_TAKEN`, 409).
6. **The display point is made when the property is** (`domain/location.py`):
   - **How:** the exact point moved 80 to 150 m in a random direction, from a CSPRNG.
   - **Stability:** it is made again only when the exact point moves, so asking repeatedly can't average it away (ARCHITECTURE §10.5).
   - **Step 2.7** keeps the exact point and the address out of public responses.
   - **Public geo queries measure from display points** (`within`, `in_bounds`). Exact distances to a few known places, campuses and stations say, would give the building away by trilateration. Search (3.2) and the map (3.3) must do the same.
   - **The exact point** is queried only to find likely duplicates when staff add a listing (`near_exact`).
7. **Slugs** come from the name and the locality (`ashas-pg-kamla-nagar`), ASCII only. A taken slug gets a number (`-2`, `-3`, …).
8. **The catalog asks the geo module for localities** through `GeoLookup`, which runs inside the caller's transaction. Shared geometry moves to core:
   - `app.core.geometry` (pure): points, bounds, distances and the NCR box;
   - `app.core.postgis`: values in, coordinates and distances out.
9. **Amenities** are a table, seeded by a data migration of their own: Wi-Fi, power backup, RO water and the like.
   - **Slugs are permanent** because search filters on them.
   - **Not here:** what belongs to a room (AC, an attached bath, a balcony) is on the room category, and meals are on the property.
10. **Every change is audited** in its own transaction: an owner added, a property created, updated (which fields) or moved between statuses, rooms and beds added, amenities set.

## Consequences

- **Pricing** (Phase 4) can trust that every base rent is positive and within the owner's range, and that each category's charges can be totalled for a quote.
- **Bookings** (Phase 5) hang their inventory allocations off `beds`, and a booking's category, room and bed belong together by construction.
- **Search and the map** must use `display_location` for anything public, distances included.
- **Step 2.6** adds the GSTIN's check digit; for now only its shape is checked.
