---
name: slice-thin
description: Cut an end-to-end walking skeleton.
---

# Skill: slice-thin

**Purpose:** Cut an end-to-end walking skeleton.

**When to use:** A slice is becoming a platform layer.

**Steps:**
1. Pick a user-visible outcome.
2. Walk every activity with the thinnest task.
3. List what is out of the slice.
4. Name a demo that a user would recognize.

**Failure modes:**
- Horizontal layer cake

**Eval hooks:** schema-valid, oracle-refuse-honored

**Abort:** If input fails schema, if required citations are missing when the skill claims evidence, or if a refuse rule in the delivered knowledge/PRINCIPLES.md and Station policy matches.


## Native execution contract

Resolve the owning instance/Workstation and exact generated role map before using this skill. Use native skill discovery to resolve the absolute path of this installed SKILL.md. Its third parent is PROFILE_ROOT (the parent of skills/). Resolve the concrete absolute RUNNER at PROFILE_ROOT/programs/runner.py; resolve input.schema.json and output.schema.json beside this skill and knowledge files under PROFILE_ROOT. Do not guess from HERMES_HOME: it can denote the base home or the active profile. Read knowledge/PRINCIPLES.md and relevant knowledge/BOOKS.json/PRACTICES.json entries there. Imported confidence is reported, not verified. Station rules override the input Oracle.

Validate the supplied input with python3 -I -B ABSOLUTE_RUNNER validate --skill slice-thin --kind input --input ABSOLUTE_WORKSPACE_INPUT.json. Perform the declared reasoning without changing accounts, services, external trackers or source software. Emit the complete typed artifact, including mandatory confidence A–E, evidence references and assumptions. Validate it with python3 -I -B ABSOLUTE_RUNNER validate --skill slice-thin --input ABSOLUTE_WORKSPACE_OUTPUT.json before returning it to the Director. Empty evidence means no source verification, never accepted confidence by itself.

Replace the symbolic absolute-path labels above with the discovered concrete paths in argv, not an evaluated shell expression. Keep native cwd in the owning workspace; never write artifacts into PROFILE_ROOT or the immutable source. The runner is read-only and emits a content hash. The authorized executor may persist the artifact/receipt only in the owning workspace. Missing fields, invalid journey slices, dependency cycles, unsupported guarantees or an unknown owner stop the workflow; retain partial artifacts and request a bounded correction. Human acceptance and behavioral evaluation remain separate from schema validity.
