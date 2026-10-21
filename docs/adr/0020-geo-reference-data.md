# ADR 0020: Geo reference data from OpenStreetMap and Wikidata, generated rather than typed in

- Status: accepted
- Date: 2026-10-21
- Build step: 2.1 (geo seed)

## Context

Search, the map, campus pages and rent bands all depend on places:
- cities;
- the localities where PGs are;
- the campuses students search near;
- the metro stations they travel from.

CLAUDE.md forbids invented coordinates. Step 2.1 says to take them from OpenStreetMap (with attribution) or official sources, and to leave out anything that can't be verified. The data must load the same way locally, in tests and in production, and loading it twice must do no harm.

What doing it turned up:
- **Overpass is out.** OpenStreetMap's read-only query service is unreachable from the development network.
- **The OSM editing API is out.** It is "not for read-only purposes or projects" (its usage policy).
- **Nominatim is usable, under a policy** (https://operations.osmfoundation.org/policies/nominatim/):
  - at most one request a second;
  - a User-Agent that identifies the application;
  - results cached;
  - no bulk or systematic queries.

  Code written by an LLM must follow all of it too.
- **Metro lines live elsewhere.** A station node doesn't name its lines; route relations do, and reading those needs Overpass. Wikidata (CC0) links each station to its lines (P81, "connecting line") and each line to its colour (P465).

## Decision

1. **Two files in `apps/api/src/app/modules/geo/data/`.**
   - `places.toml` is written by hand. For each place it holds our slug and name, and the OpenStreetMap element it is; for each metro line, its Wikidata item.
   - `places.json` is generated, and is what `make seed` loads. It holds the coordinates, the boundaries and each station's lines. Nobody edits it by hand.
   - **A unit test fails** when the two files disagree, or when the JSON isn't exactly in the generator's format. Neither can change alone.
2. **`make geo-refresh`** (`app/modules/geo/refresh.py`) writes `places.json`.
   - **How it asks:**
     - **Nominatim:** only `/lookup` by element id, at most 50 elements a request. It never searches: choosing the right element is a person's job, done once per place.
     - **Wikidata:** `wbgetentities`, with `maxlag`.
     - **Pace:** one request at a time, at most one a second, with a User-Agent that names the project.
     - **Cache:** answers are kept on disk for a day (`apps/api/.cache/`, gitignored), so a second run asks only for what changed.
   - **What it refuses**, rather than guess:
     - an element Nominatim doesn't have;
     - a "station" that isn't a metro station: it must have `station=subway` or similar, because mainline stations are `railway=station` too;
     - a station that OpenStreetMap and Wikidata place more than 300 m apart, since two independent sources must agree;
     - a station on a line the manifest doesn't list. It prints the entry to add.
     - a line with no colour.
   - **What it ignores:** Wikidata statements that are deprecated, have ended, or haven't started yet.
   - **What it reports:** a note wherever our name differs from OpenStreetMap's ("Gurugram", where OpenStreetMap says "Gurgaon").
   - **When it writes:** never if only the date would change.
   - **Where it runs:** never in CI or tests. Tests use stand-ins for both services.
3. **What is seeded** (retrieved 2026-10-21):
   - **Cities:** 3 (Delhi, Gurugram, Noida).
   - **Localities:** 13, around North Campus and Satya Niketan. 10 have boundaries; three are mapped as points.
   - **Campuses:** 19 — North Campus as a whole, 11 North Campus colleges and departments, and 7 South Campus colleges.
   - **Metro stations:** 14, on 6 lines, near those places.

   Left out, and listed in the manifest:
   - **Old Rajinder Nagar:** OpenStreetMap has no place, boundary or address by that name.
   - **The Gurugram and Noida hubs:** the founders haven't named them yet.
   - **South Campus as a whole:** no single OpenStreetMap feature covers it, so its colleges stand for it.
4. **Tables** (ARCHITECTURE §6): `cities`, `localities`, `campuses`, `metro_lines`, `metro_stations` and `metro_station_lines`.
   - **Geometry:** `geography` in WGS 84, so distances are metres on the ellipsoid. GiST indexes serve nearest-first ordering (`<->`) and `ST_DWithin`, and a trigram index serves locality names.
   - **Boundaries** are MultiPolygons, since an OpenStreetMap area can come in several pieces.
   - **Provenance:** each row keeps its OpenStreetMap element, and lines and stations keep their Wikidata item.
   - **Lines have their own table** because interchanges are on several: Kashmere Gate is on three.
   - **Slugs are the public keys** (`/pg-in/[locality]`, `/pg-near/[campus]`), so there are no public ids.
   - **GeoAlchemy2** provides the column types (the decided stack). Its automatic spatial indexes are off, so these are named like every other index.
5. **Loading** (`python -m app.manage geo load`, which `make seed` runs):
   - **Matching:** rows are matched by slug.
   - **Transactions:** one transaction, with an advisory lock against a second load running at the same time.
   - **Writes:** only rows whose values changed are written, with geography compared as WKB, which is exact. A second load writes nothing.
   - **Audit:** an entry, carrying the data's SHA-256, is written only when something changed.
   - **Rows the data drops** are counted but left alone, since properties may refer to them. Removing one is a migration's job.
   - **Production:** this is reference data, not sample data, so production loads it too, after migrations, whenever `places.json` changes (runbook: geo data).
6. **The public API:**
   - **Routes:** `GET /v1/cities`, `GET /v1/localities?city=`, `GET /v1/campuses?city=`, `GET /v1/campuses/{slug}` and `GET /v1/metro-stations`.
   - **Access and caching:** anyone may read them (they are in the authorization matrix), with `Cache-Control: public, max-age=3600`.
   - **No paging:** the lists come whole. They hold curated reference data (dozens of rows), and adding a cursor later is backwards compatible, since `{items}` becomes `{items, nextCursor}`.
   - **Order:** by lower-cased name, byte by byte, then slug. Every environment then sorts the same way, whatever its database's locale; glibc's `en_US`, for one, ignores spaces.
   - **Campuses** come with their nearest metro station. A campus page adds its three nearest stations, and the localities within 2 km (measured to the boundary, 0 inside it), the radius a first micro-market maps.
   - **Distances** are whole metres, from PostGIS.
   - **Query counts:** each response takes a fixed number of queries, however many rows.
7. **Attribution:**
   - **Licence:** `places.json` is a database derived from OpenStreetMap, so it is available under the ODbL (`data/README.md`).
   - **Credit in the product:** wherever the product shows this data (map overlays, distances on cards and pages), it credits "© OpenStreetMap contributors" with a link to https://www.openstreetmap.org/copyright. That arrives with step 3.4 and step 3.5.

## Consequences

- **Adding a place** takes a manifest line, `make geo-refresh` and a reviewed diff. In the diff, the coordinates arrive from the tool.
- **The founders can fill the gaps:**
  - by naming the Gurugram and Noida hubs;
  - for Old Rajinder Nagar, by mapping it in OpenStreetMap (anyone may, and the data is then everyone's), or by naming an official source.
- **A new line stops the refresh.** A station on a line the manifest doesn't list (Delhi Metro's Phase 4 lines, say) stops the refresh until someone adds the line.
- **The OSM credit is separate** from the map provider's own attribution, and the map overlays must carry it.
- **Deploys** run `geo load` after migrations whenever `places.json` has changed.
