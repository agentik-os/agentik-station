# Builder Repository / Distribution Drift Checks

Builder Doctor must detect documentation/runtime drift instead of trusting prose.

## Required checks

### Declared artifact exists
If README/manifest claims `scripts/`, `tests/`, `recovery/`, `evidence/` or another artifact, the release fails when it is absent.

### Provider source of truth
Provider/model intent must be role-based and compiled by Station/AGK. Conflicting primary/fallback declarations across config/distribution are release drift.

### Discord token semantics
Bot tokens remain external secret references and may be absent at package construction time, but a canonical OS cannot pass `DISCORD_BOUND`, fresh-session acceptance or release until its dedicated Nano Director bot is actually enrolled and read back.

### Hermes compatibility
The declared Hermes requirement must match the Station lockfile and the current compiler/tests. Unknown config keys or hook contracts fail candidate release.
