# ADR 0038: Rule sets and versioning: a draft, one set in force and archived ones per PG; atomic activation that checks the set first; and triggers that keep anything once in force as it was

- Status: accepted
- Date: 2026-10-30
- Build step: 4.3 (rule sets and versioning)

## Context

- **BUILD_PLAN 4.3:**
  - rule sets go from draft to active to archived;
  - activation is atomic, creates an immutable version and is audited;
  - validation (overlapping seasons, band conflicts, impossible bounds) returns readable errors.

  It's done when activating a new version never changes existing quotes or bookings, tested.
- **ARCHITECTURE §6** has `pricing_rule_sets` (one active per PG; active and archived sets immutable) and `pricing_rules` (kind, room categories or all, params as JSON, a label, enabled). §8.2 says seasons may not overlap for the same categories.
- **Rule 5:** a quote's price is fixed for the stay, and rule changes never touch existing quotes or bookings.
- **The engine** (ADR 0037) takes typed rules. Quotes, which will name the set that priced them, come in step 4.4.

## Decision

1. **Versions per PG:** at most one draft and one active set (partial unique indexes), each numbered from 1.
   - A draft starts empty for a PG's first set, or as a copy of the set in force.
   - Only a draft's rules change: they're added, replaced and removed in the set's order.
   - Discarding deletes a draft and nothing else.
2. **Activation is one transaction under the PG's advisory lock.**
   - It checks the draft. If it's clean, the set in force becomes `archived`, with `archived_at` the same instant as the draft's `activated_at`, and the draft becomes `active`.
   - It's audited with both versions, the rule count and the note.
   - There is no moment with two sets in force, or none.
3. **Database triggers back the immutability.** The service refuses such changes first, with 409 `INVALID_TRANSITION`.
   - `pricing_rules_only_in_drafts` refuses inserting, changing or deleting a rule of a set that isn't a draft. It allows a draft's rules going with their set.
   - `pricing_rule_sets_only_forward` refuses deleting a set that isn't a draft, moving a set back, or changing an active set except to archive it. An archived set never changes.

   So nothing behind the API's back can change what a set priced.
4. **Checks before activation** (`rule_set_problems`, pure), each in words ops can act on, against the PG's active room categories and the band in force for each category's locality and occupancy:
   - seasons that overlap for a category, the year's wrap included;
   - overrides that overlap for a category;
   - bounds that leave no rent (owner bounds against the band);
   - an override's rent outside the band;
   - rules for room categories the PG doesn't have;
   - more than 30 rules.

   They answer **422 `RULE_SET_INVALID`** with every problem. A draft's view lists the same problems as they stand, so ops see them before trying.
5. **Rules are typed in and out.**
   - The API takes a rule's parameters as a union discriminated by `kind`: `season`, `occupancy`, `early_bird`, `last_minute`, `length_of_stay` or `override`.
   - The engine's types check them, and a rule that can't be answers `RULE_SET_INVALID`.
   - They're stored as JSON in the domain's own shape (`params_to_json` / `params_from_json`), read back with type checks. A property test proves every rule comes back as it went in.
   - Room categories are public ids in the API and internal ids in the row.
6. **Ops and admins** in a staff session use `/v1/ops/properties/{id}/rule-sets` (+ `/draft`), `/v1/ops/rule-sets/{id}` (+ `/rules`, `/activate`, `DELETE`) and `/v1/ops/rules/{id}` (`PUT`, `DELETE`). Owners get the same in Phase 7. The pricing editor UI is step 4.6.
7. **The coverage gate** (ADR 0037) now covers `rule_sets.py` too.

## Consequences

- **The "done when" for now.** Until 4.4's quotes exist, a test prices with a set's stored rules before and after the next version is activated, and the price is the same. It also checks that the archived set reads back unchanged and that the database refuses edits. 4.4 adds the same check on stored quotes.
- **Search** still shows listed rents (ADR 0027). Step 4.5 brings quote-consistent prices to the PG page.
- **CI time.** The API job now takes about 14 minutes with the engine's 10,000-case properties. If more property tests push it towards the 30-minute limit, the properties should run in parallel (pytest-xdist).
