---
name: shape-bet
description: Shape a time-boxed bet.
---

# Skill: shape-bet

**Purpose:** Shape a time-boxed bet.

**When to use:** Work is about to enter a cycle unshaped.

**Steps:**
1. State problem and appetite.
2. Fat-marker solution.
3. List rabbit holes and no-gos.
4. Write the pitch as a bet, not a backlog forever.

**Failure modes:**
- Wish with a date

**Eval hooks:** schema-valid, oracle-refuse-honored

**Abort:** If input fails schema, if required citations are missing when the skill claims evidence, or if a refuse rule in the delivered knowledge/PRINCIPLES.md and Station policy matches.


## Native execution contract

Resolve the owning instance/Workstation and exact generated role map before using this skill. Use native skill discovery to resolve the absolute path of this installed SKILL.md. Its third parent is PROFILE_ROOT (the parent of skills/). Resolve the concrete absolute RUNNER at PROFILE_ROOT/programs/runner.py; resolve input.schema.json and output.schema.json beside this skill and knowledge files under PROFILE_ROOT. Do not guess from HERMES_HOME: it can denote the base home or the active profile. Read knowledge/PRINCIPLES.md and relevant knowledge/BOOKS.json/PRACTICES.json entries there. Imported confidence is reported, not verified. Station rules override the input Oracle.

Validate the supplied input with python3 -I -B ABSOLUTE_RUNNER validate --skill shape-bet --kind input --input ABSOLUTE_WORKSPACE_INPUT.json. Perform the declared reasoning without changing accounts, services, external trackers or source software. Emit the complete typed artifact, including mandatory confidence A–E, evidence references and assumptions. Validate it with python3 -I -B ABSOLUTE_RUNNER validate --skill shape-bet --input ABSOLUTE_WORKSPACE_OUTPUT.json before returning it to the Director. Empty evidence means no source verification, never accepted confidence by itself.

Replace the symbolic absolute-path labels above with the discovered concrete paths in argv, not an evaluated shell expression. Keep native cwd in the owning workspace; never write artifacts into PROFILE_ROOT or the immutable source. The runner is read-only and emits a content hash. The authorized executor may persist the artifact/receipt only in the owning workspace. Missing fields, invalid journey slices, dependency cycles, unsupported guarantees or an unknown owner stop the workflow; retain partial artifacts and request a bounded correction. Human acceptance and behavioral evaluation remain separate from schema validity.
