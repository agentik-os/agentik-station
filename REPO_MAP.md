# Repository Map

The full human-readable map is [`atlas.md`](atlas.md). Canonical reusable resources are under `resources/`, universal executor rules under `rules/`, OS sources under `os/`, and the Station kernel under `src/agentik_station/`.

```text
agentik-station/
├── src/agentik_station/        v11 typed safe-kernel implementation
├── installer/                  thin privileged entrypoint
├── station                     repository CLI
├── install                     apply wrapper
├── config/                     canonical desired-state defaults/examples/schemas
├── contracts/                  machine-readable kernel/module contracts
├── modules/                    truthful module maturity catalog
├── runtime/                    systemd, Hermes plugin/hook/program scaffolds
├── os/                         single canonical AGK OS v2 source tree and catalog
├── factory/                    canonical Builder/Librarian programs/contracts/tests
├── specs/                      OS, Discord, Composio, orchestration implementation specs
├── templates/                  Zone/Project/system templates
├── docs/                       current architecture and domain documentation
│   ├── hardening/              v11 audit response and release gates
│   ├── audit/                  source audit/evidence that drove v11
│   └── history/                non-canonical provenance
├── docs/history/                non-canonical provenance and prior snapshots
├── tests/                      unit, security, contract, and temp-root integration tests
└── .github/                    CI and contribution templates
```

Canonical editable OS sources live only in `os/`; Builder orchestration programs live in `factory/programs/`. Generated Hermes distributions are disposable artifacts, never parallel editable source trees.

## Operator entry points

- `station` — canonical Python CLI and source of truth.
- `install` — minimal apply entry point.
- `station.sh` — one-command Bash orchestration wrapper for Doctor → spec → plan → apply → Doctor → status.
