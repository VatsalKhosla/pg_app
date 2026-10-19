# ADR 0017: Authorization: one actor dependency, policy functions and a hand-written matrix

- Status: accepted
- Date: 2026-10-19
- Build step: 1.4 (policies and the authorization matrix)

## Context

ARCHITECTURE §12 and CLAUDE.md set three requirements:
- Every route authorizes, deny by default.
- Another user's record answers 404.
- An authorization matrix test covers every endpoint and every role.

Steps 1.1 to 1.3 authorized the identity routes as they were built. But the current actor came from the identity module (`identity/auth.py`), so every later module's routes would have had to import identity's internals. This step makes the pattern explicit, and enforced, before the catalog, booking and payment modules arrive.

## Decision

1. **One actor dependency, in core** (`app/core/current_actor.py`):
   - `CurrentActor` is the signed-in user, and answers `401 UNAUTHENTICATED` without a live session. `OptionalActor` is None instead, for routes anyone may call that tell a signed-in user more.
   - Core declares an `Authenticate` interface. The composition root sets `app.state.authenticate` to the identity module's session check (`authenticate_session` in `identity/auth.py`).
   - Every module's routes therefore depend on core, never on identity. FastAPI resolves the actor once per request.
2. **Policy functions** live in each module's `policies.py`. They are pure functions named `can_<do>_<what>(actor, ...)`, returning a bool. They take the `Actor` and the facts the decision needs, such as ids and statuses, never a database session. They are unit tested for every role.
3. **Which answer:**
   - **No live session:** `401 UNAUTHENTICATED`, from `CurrentActor`.
   - **A role the session doesn't carry:** the route raises `ForbiddenError`, answering `403 FORBIDDEN`. The route itself is no secret: it is in the OpenAPI schema.
   - **Someone else's record:** `404 NOT_FOUND`, exactly as if it didn't exist. The service asks the policy with the record's owner and returns nothing, so the record's existence never leaks.
   - **Business refusals** keep their own codes: `STAFF_ACCOUNT_NOT_ALLOWED` now, `BED_UNAVAILABLE` and others later.

   So a router resolves the actor, asks a policy for role checks, and calls one service method, which applies the object-level policies (the backend rules' layering).
4. **The authorization matrix** (`apps/api/tests/authorization.py`) is written by hand, apart from the routes themselves. For each `(method, path)`, it gives the status each of eight callers gets:
   - **Anonymous.**
   - **In user sessions:** a student, a parent, an owner, and an admin signed in by phone. User sessions never carry staff roles.
   - **In staff sessions:** a field agent, ops and an admin.

   Two tests enforce it:
   - **Coverage:** `tests/unit/test_authorization_coverage.py` needs no Docker. It fails when a route has no entry, an entry has no route, an entry leaves a caller out, or a path parameter names a kind of record the matrix can't make. A new route can't merge without saying who may call it.
   - **Behaviour:** `tests/integration/test_authorization_matrix.py` calls every route as every caller against PostgreSQL and Valkey and lists every mismatch. Each call gets a fresh session (some routes end it), a valid CSRF token, and someone else's records in the path.

   Because the table is kept apart from the route code, changing who may call a route shows up twice in review: once in the route, once in the matrix.

## Consequences

- **New modules** take the actor from `app.core.current_actor`, so the identity module stays out of their routers' imports.
- **Each new route** needs a matrix entry. A path parameter naming a new kind of record also needs a way to make one for someone else. The matrix grows with the ops console (Phase 2), bookings and payments, and its run time grows with routes times callers.
- **Statuses, not bodies:** the matrix checks statuses only. A leak inside a 200, such as another user's data in a list, is for the module's own tests to catch, as the staff list's tests do.
