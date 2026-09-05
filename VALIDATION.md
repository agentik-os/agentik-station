# Agentik Station 11.14 Validation

Local verification on 2026-09-05, after the client-owned OS instance implementation:

- Full Station/Factory suite: **691 passed** (687 Station + 4 Factory).
- A final narrow maturity correction then distinguished an incomplete first
  installation from degradation of a previously configured instance. Its impacted
  lifecycle, instance, CLI and onboarding suites passed **161 tests**, including
  one additional regression. Final inventory: **692 tests** (688 Station + 4 Factory).
- Shipped AGK-TUI component suite: **224 passed, 1 sandbox-denied socket test,
  2 skipped** on its first run. The exact socket test passed with the required
  local Unix-socket permission (**225 unique passing tests**). The two skips are
  absent local Crawl4AI/ScrapeGraphAI libraries; dedicated CI jobs exercise them.
- Builder/Librarian deterministic gates: **7/7 passed**.
- Repository Doctor: **PASS**, no issues or warnings.
- Shell syntax, Python AST, JSON/YAML parsing, release schema, exact inventory and
  deterministic SBOM/provenance checks: **PASS**.
- README/atlas presentation: **20 focused contract tests**, **113 local links**
  and **16 new CLI examples** checked; four changed SVGs rendered and visually
  inspected at 830px and 390px. Mermaid source was reviewed, not live-rendered on GitHub.

Tests use temporary filesystem fixtures and simulated native Hermes commands where
needed. The new cross-module regression registers a real Organization over its
canonical client Zone, compiles the real DevOps source into two instances, installs
both complete teams through a fake native installer, verifies them and resolves
their distinct Directors/Hermes homes/native service names through actual
onboarding and gateway builders. No Project owner is required. Legacy runtime
tests remain covered. All six source packages compile instance-local voice defaults.

This is source/local evidence for a **READY_FOR_SETUP** foundation, not a real VPS
or `OPERATIONAL` claim. Native Linux publication, platform behavior and external
accounts require their corresponding evidence. The separately dispatched disposable
VPS workflow was not run for this local validation. No live bot, paid provider,
Strix scan or off-Host recovery acceptance is implied.

Same-Zone instances share a Unix UID and canonical Zone HOME; declared Project
scope is not a filesystem sandbox. Restored/replaced instance roots need reviewed
repair because their inode evidence cannot be silently adopted. The guided broker
and legacy AGK client/dashboard do not automatically become instance-aware.

Follow the [first-mission sequence](docs/operations/06_FIRST_MISSION.md),
[setup gates](SETUP.md) and [instance contract](docs/organization/05_OS_INSTANCES.md).
The [11.13 audit](docs/audit/2026-09-05-operational-control-plane.md) records the prior lifecycle review.
[`VALIDATION_11_12.md`](VALIDATION_11_12.md) remains historical release evidence.
