# Geo data

Use this for adding or correcting a city, locality, campus or metro station, for a `make geo-refresh` that refuses, and for loading the data into an environment. The design is in [ADR 0020](../adr/0020-geo-reference-data.md).

Two files in `apps/api/src/app/modules/geo/data/`:
- `places.toml` is written by hand.
- `places.json` is generated from it and is what gets loaded. Never type a coordinate into either.

## Add or correct a place

1. **Find the element** on https://www.openstreetmap.org: search for the place, open the result, and note its type and number from the address bar, such as `relation/3859752`.
   - **A locality:** prefer an area, a `boundary=administrative` relation or a `place=*` area, so it keeps its outline. A point works but has no boundary.
   - **A campus:** the college's grounds, usually an `amenity=college` or `amenity=university` way.
   - **A metro station:** the station itself (`railway=station` with `station=subway`), never an entrance or a stop position. Mainline stations are `railway=station` too, but carry `train=yes` and `network=IR`.
2. **Add an entry** to `places.toml` with a slug (lowercase words joined by hyphens), our name and the element.
3. **Run `make geo-refresh`.** It asks Nominatim and Wikidata (network) and writes `places.json`.
4. **Read the notes:**
   - A name note means OpenStreetMap names the place differently. Keep ours only on purpose, for example the official "Gurugram" rather than "Gurgaon".
   - A "mapped as a point" note means the locality has no boundary.
5. **Review the diff:** the new rows should look right, and nothing else should move unless OpenStreetMap changed.
6. **Load it locally** with `make seed`. If you like, check the campus page: `curl localhost:8000/v1/campuses/<slug>`.
7. **Commit both files together.** `make check` fails if they disagree.

## When the refresh refuses

It names the place and the problem:

| It says | Do |
|---|---|
| `Nominatim has no <element>` | Check the type and number on openstreetmap.org. The element may have been deleted or merged; find its replacement. |
| `... not a metro station` | You picked a mainline station, an entrance or a stop position. Pick the station element. |
| `... has no Wikidata item` | The station lacks a `wikidata=*` tag. Choose another element of the same station, or add the tag in OpenStreetMap if you are sure of the item. |
| `OpenStreetMap and Wikidata ... are N m apart` | One source is wrong or names another station. Look at both before going on, and fix the wrong one at its source. |
| `on <line> (<item>), which places.toml doesn't list` | If it is a line, paste the `[[metro_lines]]` entry it prints and check the name. |
| `no colour (P465) on Wikidata` | The line's Wikidata item lacks a colour. Add it there, citing the operator. |
| `answered 429` or `Wikidata is busy` | The service is asking us to slow down. Wait and run it again later. Don't loop it. |

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/) allows at most one request a second, from one machine, with results kept. The tool keeps to that, and keeps answers for a day in `apps/api/.cache/geo-refresh/`. `make geo-refresh args=--fresh` ignores them.

## Load the data into an environment

Run `python -m app.manage geo load` (locally `make seed`) after migrations whenever `places.json` has changed. It prints, per kind, how many rows are new and how many changed.
- **Running it again is safe:** it writes only what differs, and says "already up to date" when nothing does.
- **Audit:** a load that changes something writes a `geo.reference_loaded` audit entry with the data's SHA-256.
- **Rows the data no longer lists** are reported as "no longer listed (left alone)".

## Remove a place

The loader never deletes. A property may be in that locality, or a page may link to that campus. To remove a place:
1. Check that nothing refers to it.
2. Take it out of `places.toml` and refresh.
3. Write a migration that deletes the row, following the usual expand-then-contract steps (CLAUDE.md).
