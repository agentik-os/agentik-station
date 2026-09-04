# Agentik Station 11.12 Validation

Release claim: **READY_FOR_SETUP**. This is not a production OPERATIONAL claim.

Locally verified release gates:

- 186 Station tests + 4 Factory pytest tests PASS (190 total, September 5 audit revision);
- 215 AGK-TUI component tests PASS; 2 optional real-library tests are skipped in the dependency-light suite, then exercised separately with each actual library installed;
- Crawl4AI 0.9.3 real raw-HTML-to-Markdown conversion PASS in an isolated Python 3.13 environment;
- ScrapeGraphAI 2.2.2 actual `SmartScraperGraph.run()` PASS with a fake local model and network disabled after public tokenizer prewarming; 35 web tests pass in that isolated environment. No paid extraction was run;
- Crawl4AI isolated environment: 35 web tests PASS, including actual raw-HTML conversion;
- Strix 1.6.1 real CLI `--help` / `--version` PASS; sandbox image manifest digests observed without starting containers. Synthetic tests cover the native Hermes team/plugin, scope/identity/grant checks, source isolation, secret filtering, timeout/cancellation, clean/findings/incomplete evidence and label-scoped cleanup;
- 15 Hermes Fleet TypeScript tests plus typecheck and production build PASS in the preceding September 4 verification; frontend files were unchanged and these commands were not rerun in this audit;
- 7/7 Builder/Librarian deterministic gates PASS;

- repository Doctor;
- unit/security/contract/install test suite;
- full/core and team desired-state plans;
- Bash syntax for `station.sh` and `bootstrap.sh`;
- dedicated `agk-station` account bootstrap contract;
- pinned operator-toolchain and checksum/integrity contract;
- queryable pinned resource catalog and idempotent multi-executor Station rules;
- Hermes release-commit pin, backup/Doctor update wrapper and receipt contract;
- Zone-isolated Hermes gateway argv/alias contract;
- case-insensitive repository path portability;
- `ORGANIZATIONS` category and team member contract;
- no real-person/client/project names in the packaged source;
- six canonical AGK OS source Doctors;
- Librarian v3 canonical source and Hermes compiler path;
- release manifest / file inventory readback;
- SHA-256 release provenance, CycloneDX SBOM and source/install/loaded manifest receipt contract;
- DevOps OS semantic Doctor: six identities, typed tools/provider routes (including the bounded ScrapeGraphAI research route), closed workflow, 15 Librarian sources, 12 adversarial scenarios and recovery checksum;
- disposable Ubuntu 24.04 bootstrap workflow is implemented (weekly core profile; manual complete AI/voice profile), not yet an observed successful bootstrap for this revision;
- the new CI matrix installs each real web library and launches Chromium; execution awaits publication/authentication.

September 5 additionally repairs structured profile compilation, missing distribution
assets, root-owned OS publication, actual Zone ancestor traversal, environment
isolation, updater gateway failure, tokenizer preparation and Tailscale false
readiness. The Unix-socket AGK fixture required rerunning outside the execution
sandbox; the rerun passed. The new Linux acceptance probe runs under actual Zone
UIDs and checks both traversal and cross-Zone denial; it is implemented but not
claimed executed on a deployed Host here.

The complete findings, deliberate non-changes and remaining release/profile
migration decisions are in [the deep audit](docs/audit/2026-09-05-station-deep-audit.md).
Strix remains INSTALLABLE: no authorized target was scanned, source uploaded,
provider charged, Docker permission granted or live LAB accepted. GitHub publication
requires the OAuth `workflow` scope because the commits include CI definitions.

The previous ZIP integrity/extracted-Doctor check predates this web integration patch; no new ZIP artifact is claimed here. The web patch additionally checks public/private DNS mixtures, redirects, pinned socket connections, response bounds, worker timeouts, venv symlinks, credential filtering and native Hermes tool schemas. Compiled OS distributions include the small `station-web` plugin; these local compiler checks are not fresh-session acceptance on a live Zone.

External gates still required before OPERATIONAL: fresh VPS installation, Hermes setup/provider chat, Hermes gateway/plugin Doctor, Discord test-guild readback, Composio OAuth/MCP readback, Tailscale enrollment, off-Host backup and destructive restore rehearsal.
