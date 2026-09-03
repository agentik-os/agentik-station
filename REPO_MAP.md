# Repository Map

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
├── packages/os/                canonical OS source packages and catalog
├── factory/                    canonical Builder/Librarian programs/contracts/tests
├── specs/                      OS, Discord, Composio, orchestration implementation specs
├── templates/                  Zone/Project/system templates
├── docs/                       current architecture and domain documentation
│   ├── hardening/              v11 audit response and release gates
│   ├── audit/                  source audit/evidence that drove v11
│   └── history/                non-canonical provenance
├── source-packs/               preserved upstream/source input archives
├── tests/                      unit, security, contract, and temp-root integration tests
└── .github/                    CI and contribution templates
```

Canonical editable Builder/Librarian source lives in `packages/os/` plus `factory/programs/`. Generated distributions must be artifacts, not manually maintained duplicate source trees.
