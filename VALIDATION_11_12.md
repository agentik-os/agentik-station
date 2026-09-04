# Agentik Station 11.12 Validation

Release claim: **READY_FOR_SETUP**. This is not a production OPERATIONAL claim.

Locally verified release gates:

- 125 Station tests + 4 Factory pytest tests PASS;
- 214 AGK-TUI component tests PASS; 1 optional installed-Crawl4AI test is skipped in the dependency-light suite;
- Crawl4AI 0.9.3 real raw-HTML-to-Markdown conversion PASS in an isolated Python 3.13 environment;
- ScrapeGraphAI 2.2.2 import and real graph construction with a synthetic credential PASS; raw HTML selects `local_dir`, not URL navigation. No paid extraction was run;
- 15 Hermes Fleet TypeScript tests plus typecheck and production build PASS;
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

The previous ZIP integrity/extracted-Doctor check predates this web integration patch; no new ZIP artifact is claimed here. The web patch additionally checks public/private DNS mixtures, redirects, pinned socket connections, response bounds, worker timeouts, venv symlinks, credential filtering and native Hermes tool schemas. Compiled OS distributions include the small `station-web` plugin; these local compiler checks are not fresh-session acceptance on a live Zone.

External gates still required before OPERATIONAL: fresh VPS installation, Hermes setup/provider chat, Hermes gateway/plugin Doctor, Discord test-guild readback, Composio OAuth/MCP readback, Tailscale enrollment, off-Host backup and destructive restore rehearsal.
