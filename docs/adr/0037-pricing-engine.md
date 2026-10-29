# ADR 0037: The pricing engine: one pure, typed function from a context to a quote, every §8.8 invariant a property test, and a branch-coverage gate on the money code

- Status: accepted
- Date: 2026-10-30
- Build step: 4.2 (pricing engine)

## Context

- **BUILD_PLAN 4.2** asks for `pricing/domain/engine.py` per ARCHITECTURE §8: rule kinds with typed params, the algorithm, clamping, rounding, the fee, GST and token maths, explainable adjustments, and `engine_version`.
  - **Tests:** Hypothesis tests for every invariant in §8.8, with at least 10,000 cases in CI, plus table tests including the worked example.
  - **Done when** all invariants hold and the engine's branch coverage is at least 95%.
- **Business rules:** 2 (the fee only on the listed rent), 4 (all upside to the owner), 5 (a quote's rent is fixed), 6 (clamps) and 12 (integer paise, half-up) live here.
- **The money rules** (`.claude/rules/money-and-booking.md`): the engine takes everything through `PricingContext`, with no I/O and no clock.
- **Existing pieces:** `app/core/money.py` already had exact half-up division, `apply_bps` and `round_to_step`. Step 4.1's policies are typed values (ADR 0036).

## Decision

1. **One function**, `quote(context) -> Quote`, pure and deterministic. The context holds:
   - the room category, its listed rent and the owner's bounds;
   - the move-in, the stay, and the day it is in India;
   - the category's occupancy in basis points, which the caller counts: a secured token or later, and offline tenants, never holds;
   - the active rules, the band, and the three policies.

   It returns the monthly rent, the adjustments and clamps that explain it, the premium and discount applied, the fee, GST, the owner's total, the token, what's due at move-in, and `ENGINE_VERSION`.
2. **Rule kinds are typed values** that refuse what can't be, in `__post_init__`:
   - `SeasonRule` (month-days that may wrap the year, ±bps);
   - `OccupancyRule` (rising tiers, premiums only);
   - `EarlyBirdRule`, `LastMinuteRule` and `LengthOfStayRule` (discounts only);
   - `OverrideRule` (dates and a rent above zero).

   A `PricingRule` wraps one with its label (40 characters at most), its room categories and whether it's on. Because the discount kinds can't hold a premium, "they never raise a price" holds by construction, and a property test proves it too.
3. **The algorithm** is §8.3's, step by step. Where §8.3 is silent:
   - **Overrides:** the first matching override in the rule set's order wins. Step 4.3 refuses sets where two can match.
   - **A floor:** a rent is never below one paisa, so rounding can't make it zero.
   - **Rounding inside the bounds:** after rounding to the step, a price outside the bounds goes to the nearest multiple inside them. When no multiple fits, it goes to the bound.
   - **Impossible bounds:** if the owner's bounds and the band leave nothing (lowest above highest), it raises `ImpossibleBoundsError` and quotes nothing. The quotes API (4.4) answers `PRICING_CONFIG_ERROR` for it.
   - **Recorded clamps:** each clamp records what was asked and what was allowed, naming the band when it was the tighter bound.
4. **GST**, exclusive or inclusive by policy, follows §8.3's integer formula. An inclusive fee's GST is the fee less its net. The fee comes from `owner_fee(base, policy)` alone, so nothing else can touch it.
5. **Tests.**
   - **Table tests:** the worked example (₹10,300, a ₹3,000 fee, ₹540 GST, ₹2,000 token, ₹8,300 at move-in), seasons over the new year and 29 February, both caps, bound clamps by owner and band, bounds with no step between them, impossible bounds, an override, other categories' and switched-off rules, inclusive GST, a token above the rent, last-minute's two conditions, and every invalid rule and context.
   - **Properties:** a property per §8.8 invariant. They are: the fee depends only on the listed rent and the fee policy; the price stays inside the bounds and on a step unless none fits; both caps hold; early-bird, last-minute and long-stay rules never raise a price; occupancy applies only at its threshold; and quotes are deterministic, in non-negative whole paise, with due plus token equal to rent.
   - **Cases:** 200 per property locally and 10,000 in CI, through the existing Hypothesis profiles.
6. **A coverage gate.** `make coverage-money` (pytest-cov, branch coverage) fails below 95% for `pricing/domain`. It runs in `make check` and as its own CI step. Booking, payments and the ledger join it as they arrive (CLAUDE.md asks for at least 90%).
   - **New dependency:** pytest-cov 7.1.0, for development only.

## Consequences

- **Steps 4.3 to 4.6:**
  - 4.3 validates rule sets against this (overlapping seasons and overrides, band conflicts);
  - 4.4's quotes store the result with `ENGINE_VERSION` and an inputs hash;
  - 4.5's calendar calls it once per weekly move-in;
  - 4.6's editor previews it.
- **A change to the algorithm bumps `ENGINE_VERSION`**, so stored quotes say which engine made them.
- **Nothing calls the engine yet.** Until 4.4, what anyone pays is unchanged.
