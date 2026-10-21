# Geo reference data

- `places.toml` is written by hand: which places there are, and which OpenStreetMap element each one is.
- `places.json` is written by `make geo-refresh` and loaded by `make seed` (`python -m app.manage geo load`). Never edit it by hand.

How to add or correct a place: [docs/runbooks/geo-data.md](../../../../../../../docs/runbooks/geo-data.md). Why it works this way: [ADR 0020](../../../../../../../docs/adr/0020-geo-reference-data.md).

## Sources and licences

- **OpenStreetMap** supplies every coordinate and boundary in `places.json`, © OpenStreetMap contributors. Its data is available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) ([copyright and licence](https://www.openstreetmap.org/copyright)). `places.json` is a database derived from it, so it is available under the same licence.
- **Wikidata** supplies each metro station's lines and each line's colour, under [CC0 1.0](https://www.wikidata.org/wiki/Wikidata:Licensing).

Wherever the product shows this data, on a map or as a distance, it credits "© OpenStreetMap contributors" with a link to https://www.openstreetmap.org/copyright.
