# Trusted Coding-Agent Installation Prompt

Give the following instruction to a trusted coding agent after cloning this repository on the target VPS:

> Read `AGENTS.md`, `ARCHITECTURE.md`, `SECURITY.md`, `INSTALL.md`, `SETUP.md`, and `docs/hardening/README.md`. Treat them as authoritative. Inspect the Host without exposing secrets. Run repository Doctor and compile the exact install plan. Do not redesign Station or weaken Zone boundaries. Apply only the supported safe-kernel installation after the plan is reviewed. Then run installed-Host Doctor and report the exact observed state, completed receipts, warnings, degradation, and next setup gates. Leave the Host at `READY_FOR_SETUP`. Do not claim Hermes, Discord, Composio, Tailscale, GitHub credentials, OS packages, remote Fleet, backup, or recovery are ready unless their real module-specific Doctor/readback/acceptance evidence exists.

Expected base flow:

```bash
cd agentik-station
./station doctor --repo
./station plan --host-id <host-id> --role <role>
sudo ./install --host-id <host-id> --role <role>
station doctor --full
station status --json
station module status
station provider status
station deps toolchain-check
```

For a seeded organization/project Host, use the exact command pattern in `INSTALL.md` or a reviewed JSON `InstallSpec`.

The installation report must separate:

- plan prepared;
- actions observed;
- installer-reported completion;
- Doctor-verified foundation;
- modules still awaiting configuration/readback;
- final state and next repair/setup action.

## Preferred installation command

After reading the repository contracts, an AI operator should prefer:

```bash
sudo ./bootstrap.sh --mode full
```

Use `--with-ai-stack` only when Ponytail, Langfuse, Honcho, Hindsight, TigerVNC and Crawl4AI are all desired on this Host. Do not use `--yes` until the generated plan has been inspected. Bootstrap installs pinned binaries but never authenticates GitHub, Vercel, Composio, Codex, Hermes providers or messaging platforms on the operator's behalf.
