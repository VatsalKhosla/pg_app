---
name: next-step
description: Implement the next unchecked step in docs/BUILD_PLAN.md, or the step id given, using the plan → build → test → tick workflow.
disable-model-invocation: true
---

Work on build-plan step $ARGUMENTS. If no step id was given, use the first unchecked step in `docs/BUILD_PLAN.md`.

1. Find the step in `docs/BUILD_PLAN.md`. If an earlier step is still unchecked, say so and ask whether to continue anyway.
2. Read the ARCHITECTURE.md sections the step relies on, plus `docs/PRODUCT_CONTEXT.md` if the step touches money, pricing, booking, trust copy or legal pages.
3. Look at the existing code for anything already built for this step.
4. Write a plan: goal, files to add or change, migrations, endpoints, UI, the key test cases by name, risks and open questions. For anything touching money, inventory or auth, present the plan and wait for approval before coding.
5. Implement in small commits, writing tests alongside the code.
6. Run `make check` and fix everything. Never skip, delete or weaken a test to get green.
7. Walk through the step's "Done when" and the Definition of Done at the top of the plan, with evidence for each item (test names, commands, screenshots for UI where possible).
8. Tick the step in `docs/BUILD_PLAN.md` and add a one-line note under it: what was built, and anything deferred and why.
9. Summarise for the founders: what changed, how to try it locally, and anything that needs their decision. Then stop.
