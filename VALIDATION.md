# Agentik Station 11.13 Validation

Local verification on 2026-09-05, after the owned-orchestration implementation:

- Station unit/security/contract/temp-root tests: **532 passed**.
- Factory pytest tests: **4 passed** (536 combined).
- Shipped AGK-TUI component tests: **225 passed, 2 skipped** locally because the
  isolated Crawl4AI/ScrapeGraphAI libraries are absent. Dedicated CI jobs install
  those libraries and exercise their actual offline runtimes.
- Builder/Librarian deterministic gates: **7/7 passed**.
- Repository Doctor: **PASS**, no issues or warnings.
- Shell syntax, Python AST, JSON/YAML parsing, release schema, exact inventory and
  deterministic SBOM/provenance checks: **PASS**.

Tests use temporary filesystem fixtures and simulated native Hermes commands where
needed. The cross-module regression creates a canonical Project, compiles the real
DevOps source, installs its complete team through a fake native installer, verifies
it and resolves the Director through the actual onboarding report.

This is source/local evidence for a **READY_FOR_SETUP** foundation, not a real VPS
or `OPERATIONAL` claim. Native Linux publication, platform behavior and external
accounts require their corresponding evidence. The separately dispatched disposable
VPS workflow was not run for this local validation. No live bot, paid provider,
Strix scan or off-Host recovery acceptance is implied.

Follow the [first-mission sequence](docs/operations/06_FIRST_MISSION.md),
[setup gates](SETUP.md) and [11.13 review](docs/audit/2026-09-05-operational-control-plane.md).
[`VALIDATION_11_12.md`](VALIDATION_11_12.md) remains historical release evidence.
