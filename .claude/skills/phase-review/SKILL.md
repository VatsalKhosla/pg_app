---
name: phase-review
description: Review a finished build-plan phase against its done-when criteria, the business rules and the security checklist, and write a gap report.
disable-model-invocation: true
---

Review phase $ARGUMENTS of `docs/BUILD_PLAN.md`.

1. List every step in the phase with its status and flag any that are unchecked.
2. Run `make check` and the phase's E2E tests; report the results.
3. For each step, verify its "Done when" with evidence: tests, endpoints, screens.
4. For each business rule in CLAUDE.md that the phase touches, name the test that protects it, or flag it as unprotected.
5. Security pass over the phase's surface: authorization matrix entries, input validation, rate limits, secrets handling, personal data in logs, headers, dependency audit output.
6. Performance pass: `EXPLAIN ANALYZE` on the heaviest new queries, N+1 checks, bundle size of new pages against the budget.
7. Write the report to `docs/reviews/phase-<n>.md` with what passed, each gap with a severity, and recommended fixes. Don't fix anything until the founders approve.
