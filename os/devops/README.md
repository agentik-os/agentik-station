# DevOps OS

Canonical engineering OS for Station. Hermes is the execution kernel. It applies Plan First, Build with Leverage, Ponytail, subagent/parallel engineering, worktree isolation, Verification Engineering, Gauntlet Loop, executor-neutral coding, CI/readback and Evidence Before Claims.

Atlas owns the mission graph. Architect owns design/contracts, Forge implementation/tests, Sentinel independent security and quality, Release Engineer reproducibility/CI/staging/approved promotion, and SRE runtime health/recovery. Model providers are replaceable cognition routes; Hermes retains session, delegation, tools, state and evidence coordination. Production remains denied without explicit human policy authority.

## Executable anatomy

- `semantics/CONTRACT.json` binds identity, authority, programs, idempotency,
  recovery and every mandatory semantic file.
- `programs/runner.py` validates the package/evidence and produces a read-only
  drift report.
- `tools/CONTRACTS.json` is default-deny and declares role, authorization,
  timeout, idempotency, audit and fallback for every exposed tool.
- `research.scrape` routes Atlas through the Zone-local Hermes
  `station_scrapegraph` tool, with `station_crawl4ai` as the explicit fallback;
  public-URL policy and evidence are mandatory.
- `providers/ROUTES.json` routes task classes, budgets, fallbacks and degraded
  behavior without changing authority.
- `workflows/STATE_MACHINE.json` is the closed tracker-neutral state graph and
  receipt contract.
- `discord/COMPONENTS.json` defines the seven authorized human controls; the
  bot identity is outside model control.
- `data/CLIENT_OPERATIONS.schema.json` validates the operational completeness
  of each client.
- `librarian/INPUTS.json` maps exactly 15 bounded authoritative inputs to
  concrete system decisions.
- `evals/SCENARIOS.json` contains 12 negative/adversarial acceptance cases.
- `recovery/BASELINE.json` is the exact checksum-bound recovery baseline.

Run `station os doctor --id devops-os` or
`./programs/runner.py validate-package --source .` from this directory. Passing
source checks means the OS is installable; it does not claim that a Zone,
Hermes profile, Discord application or provider account is operational.
