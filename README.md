# PG booking platform — starter kit for Claude Code

This folder holds no code yet. It gives Claude Code everything it needs to build the platform properly: the business rules, the architecture and a step-by-step plan.

## How to start
1. Copy this whole folder (including the hidden `.claude` folder) into an empty project folder or a new GitHub repository. On a Mac, press Cmd+Shift+. in Finder to see hidden folders.
2. Open the folder in VS Code and start Claude Code there.
3. Paste the kickoff prompt from the bottom of `docs/BUILD_PLAN.md`.
4. After that, type `/next-step` to build one step at a time, and `/phase-review 3` (for example) at the end of each phase.

## What's inside
| File | Purpose |
|---|---|
| `CLAUDE.md` | Loaded automatically every session: the product in brief, the 12 business rules, the stack, commands and how to work |
| `docs/PRODUCT_CONTEXT.md` | The business behind the code: fees, dynamic pricing, trust design, leakage, regulation, open decisions |
| `docs/ARCHITECTURE.md` | System design, data model, booking state machine, pricing engine, payments and ledger, map, security, scaling, testing |
| `docs/BUILD_PLAN.md` | Phases 0–9 with numbered steps and "done when" checks, plus the founders' parallel tasks |
| `.claude/settings.json` | Stops Claude Code reading `.env` files and keys, and pre-approves the safe `make` commands |
| `.claude/rules/` | Backend, frontend, money and security rules that load only when Claude edits matching files |
| `.claude/skills/` | The `/next-step` and `/phase-review` commands |

## Do these yourselves in week 1
The founders' task list at the top of `docs/BUILD_PLAN.md` has the jobs Claude Code can't do. Start SMS DLT registration and Razorpay KYC first, because they take the longest.
