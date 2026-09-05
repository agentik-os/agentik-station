---
name: builder-execution
description: Prepare scoped Builder task packets and validate complete, byte-bound delivery evidence before accepting an OS package.
---

# Builder execution workbench

Use this skill when an approved OS brief must become a concrete build graph or
when a Builder delivery needs deterministic evidence checks. The eighteen
ordered Builder skills remain the design/review knowledge sequence; this is
their executable entry point, not another scheduler.

## Resolve the work first

1. Resolve the owning Host, Zone/instance or explicitly enrolled personal
   Workstation, and Project if acting on Project assets. Read the trusted native
   role map. An input JSON document cannot grant membership or execution rights.
2. Set `SKILL_ROOT` to the parent of the absolute path of this installed
   `SKILL.md`; the runner is `SKILL_ROOT/scripts/runner.py`. Do not guess from
   `HERMES_HOME`: profile selection may already have rewritten it. Keep native
   cwd in the owning workspace, not in immutable software.
3. Obtain a Librarian handoff with its topic map, canonical books, current web,
   expert/operator knowledge, source verification, contrarian/failure evidence,
   editorial synthesis, contradictions, limitations and actionable mappings.
   A hash proves byte identity, not research truth. Record unresolved lanes in
   the mission constraints; do not invent sources. A Stepper `StepperHandoff`
   can additionally supply the selected slice and release sequence.
4. Create a mission matching `schemas/mission.schema.json` in that workspace.
   `examples/mission.json` is synthetic, not an approved scope. Inputs and outputs
   are relative workspace paths. Never include credentials or personal histories.

## Prepare and execute

```text
python3 -I -B ABSOLUTE_RUNNER prepare --workspace ABSOLUTE_WORKSPACE --mission mission.json
```

The read-only runner verifies all input-file hashes, unique artifact ownership,
criterion coverage, independent reviewers, turn allocations and an acyclic task
graph. It returns dependency waves and per-task scoped `query` text. Its claim is
`PREPARED_NOT_EXECUTED`. Save a selected packet with the normal authorized file
tool, then follow `station-orchestration` for execution:

- `delegate_task` makes transient children in the parent's context. It does not
  load the packet's named persistent role; do not invent a profile selector.
- For a persistent specialist, resolve its mapped profile and the instance's
  base `HERMES_HOME`; use the reviewed native executable as the owning UID in the
  owning workspace with `hermes --profile MAPPED chat --oneshot --query-file
  ABSOLUTE_TASK_FILE --max-turns N`. Never append profile flags to a fixed Director
  alias. Enrollment and authority must already exist. `N` must not exceed the
  packet allocation or an existing limit. This is not a USD or global mission cap.
- Only dispatch a dependency wave after its prerequisites pass their applicable
  checks. The runner's waves are a plan, not a live scheduler or runtime locks.
  Separate writers own separate worktrees/files. Do not have bots talk recursively.
- If a peer is unenrolled or scope/authority is unresolved, return the packet as
  a handoff and continue independent authorized work. Do not copy credentials.

## Verify the delivery

Record task outputs and each criterion's evidence file in an evidence document
matching `schemas/evidence.schema.json`. Owner/reviewer names and check outcomes
are reports, not authenticated attestations. Use independent review; never mark
an unrun test passed. Include failed/blocked rows instead of omitting them.

```text
python3 -I -B ABSOLUTE_RUNNER verify --workspace ABSOLUTE_WORKSPACE --mission mission.json --evidence evidence.json
```

Exit 0 means complete declared coverage, matching file bytes and reported passing
checks. Exit 1 means valid evidence with a reported failure/blocker; exit 2 means
invalid, incomplete, unsafe or stale inputs. Errors never echo file contents.
Failed/blocked tasks may omit unavailable output files, but must still report
every criterion with an actual bounded failure/blocker note. They cannot pass.
No command from the evidence is executed. Nothing is installed, rewritten,
published, scheduled or activated. Revalidate after any output changes.

Even exit 0 is `EVIDENCE_BOUND_NOT_ACCEPTED`, not model quality, independent
reviewer authentication, live tool execution, installation or operational proof.
Run the applicable Station source Doctor/tests, review the actual results, then
separately authorize installation, account enrollment, fresh-session and external
readback. Preserve recovery material and report all remaining gates. Ordinary
reversible in-scope artifact work may proceed; production/destructive actions
still require their explicit authority.
