# GitHub Repository Contract

The future GitHub repository created from this package should preserve this top-level contract:

```text
README.md
ARCHITECTURE.md
INSTALL.md
AI_INSTALL_PROMPT.md
AGENTS.md
CLAUDE.md
station.yaml.example
install
station
installer/
config/
runtime/
packages/
factory/
specs/
docs/
tests/
docs/history/
.github/
```

## Main branch

`main` represents the latest Station candidate that passes repository CI. Client production rollout remains controlled through Station release policy; merging `main` is not equivalent to updating every remote Host.

## GitHub CI

Every change must at minimum validate:

- Python compilation;
- JSON/YAML parsing;
- repository Doctor;
- architecture tests;
- Builder/Librarian toolchain tests;
- forbidden legacy scan;
- installer plan tests for core and remote Host roles.

## AI coding agents

`AGENTS.md` is model-neutral. `CLAUDE.md` points Claude Code to the same contract. Additional executor-specific files may be added later, but must not fork the architecture policy.

## Secrets

No real `.env`, API token, private key or production credential belongs in the repository. GitHub Actions secrets, deployment credentials and connected-account authentication remain external runtime/configuration concerns.
