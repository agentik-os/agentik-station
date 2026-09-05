# Builder OS

Builder OS is the factory that turns a mission and a Librarian handoff into a complete AGK OS package.

## Nano Director
**Master OS Builder** — accountable for the build graph, owner gates, delegation, verification and final package.

## NanoTeam
- Domain Scout — defines domain boundary, users, jobs and edge cases.
- OS Architect — designs graph, capabilities, NanoTeam, scopes and composition.
- Program Engineer — creates deterministic programs and schemas.
- Integration Engineer — defines MCP/API/Composio contracts and live tests.
- Test Engineer — test-first deterministic verification and integration fixtures.
- Evaluation Engineer — rubric, adversarial and outcome evals.
- Discord Experience Engineer — dedicated bot/channel/commands/thread behavior.
- Security & Tenancy Reviewer — permissions, secrets, isolation, data flows.
- Recovery Auditor — doctor, rollback, backup/recovery and fresh-session acceptance.
- Specification Reviewer — independent contract and completeness review.

Builder should delegate specialist tasks but the Nano Director remains accountable for release evidence.

## Executable build workflow

The native `builder-execution` skill is shipped into every Builder profile with
its standard-library runner, two strict JSON schemas and synthetic examples.
Its `prepare` command validates scope, input hashes, non-overlapping output
ownership, dependency DAG, independent reviewers and bounded turn allocations,
then emits scoped task packets. Its `verify` command requires complete task and
criterion coverage and checks actual output/evidence bytes against SHA256.

See [the installed-skill instructions](skills/builder-execution/SKILL.md) for
native path resolution, commands and the handoff protocol. The eighteen ordered
skills are retained as knowledge; the new native entry point makes their build
and review work concrete. `programs/PROGRAMS.yaml` now points to real programs,
not unimplemented command names.

Both commands are read-only and never dispatch, install, publish or activate
anything. Prepared packets are not authorization; matching hashes and reported
passing checks are not authenticated reviews, live execution or operational
acceptance. Failed and blocked checks stay visible. Existing enrolled profiles
require a separately reviewed update; source changes do not silently replace them.
