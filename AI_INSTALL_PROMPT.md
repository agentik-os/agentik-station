# Chief AI Officer AIOS — Trusted Codex Installation Prompt

Use this from a clean Ubuntu/Debian VPS session running as a newly created, non-root user with `sudo`. Codex itself should not run as root; it invokes `sudo` only for reviewed system mutations.

If the repository is not cloned yet, give Codex the repository URL and this instruction:

> Install and set up the Chief AI Officer AIOS from `https://github.com/agentik-os/agentik-station`. Clone only the canonical `main` branch with `--single-branch` into a normal user workspace. Read `AGENTS.md`, `atlas.md`, `SECURITY.md`, `INSTALL.md`, `SETUP.md` and `AI_INSTALL_PROMPT.md`. Run repository Doctor, inspect the VPS and show the exact plan before mutation. After I approve, run `sudo ./bootstrap.sh --mode full --with-ai-stack`. Then run full Doctor, status, module status and toolchain checks. Continue through setup one external gate at a time. Never request a secret in chat or place one in a command argument, Git or evidence; use each provider's native interactive login. Do not claim `OPERATIONAL` without real external readback.

Canonical clone command:

```bash
git clone --branch main --single-branch https://github.com/agentik-os/agentik-station.git
cd agentik-station
```

After cloning, the detailed operating instruction is:

> Read `AGENTS.md`, `atlas.md`, `ARCHITECTURE.md`, `SECURITY.md`, `INSTALL.md`, `SETUP.md`, and `docs/hardening/README.md`. Treat them as authoritative. Inspect the Host without exposing secrets. Run repository Doctor and compile the exact install plan. Do not redesign Station or weaken Zone boundaries. Apply only the supported safe-kernel installation after the plan is reviewed. Then run installed-Host Doctor and report the exact observed state, completed receipts, warnings, degradation, and next setup gates. Leave the Host at `READY_FOR_SETUP`. Do not claim Hermes, Discord, Composio, Tailscale, GitHub credentials, OS packages, remote Fleet, backup, or recovery are ready unless their real module-specific Doctor/readback/acceptance evidence exists.

Preferred fresh-VPS flow:

```bash
cd agentik-station
./station doctor --repo
./bootstrap.sh --mode full --with-ai-stack --plan
# Human reviews the preview. Bootstrap then revalidates and asks confirmation.
sudo ./bootstrap.sh --mode full --with-ai-stack
station doctor --full
station status --json
station module status
station provider status
station deps toolchain-check
sudo station setup --json
```

For a seeded organization/project Host, use the exact command pattern in `INSTALL.md` or a reviewed JSON `InstallSpec`.

The lower-level `station plan` / `install` path installs the typed kernel; it is
not the full dependency bootstrap. `--plan` performs read-only eligibility checks
and prints both the kernel plan and the additional shell-bootstrap operations.
Do not proceed when the Host, operator identity, checkout or immutable release
conflicts. Do not infer overall bootstrap success from a kernel receipt if a later
stage failed. Read the durable bootstrap receipt after failure. Never supply
`--acknowledge-incomplete <attempt-id>` until the human has reviewed the exact
failed stage, surviving processes and repair action; it starts a fresh attempt,
not a rollback or stage-skipping resume.

Continue with [the first-mission guide](docs/operations/06_FIRST_MISSION.md): choose
a local Zone, plan/create its Project with `station project create`, install the
owned OS, and use `station os setup` for its Director's native provider wizard.
Use `station platform setup --os <os-id>` for that Director's chat identity. Do not
fall back silently to the Zone default profile. Full/core does not invent Projects.
Safe OS retries preserve verified installed files; existing untracked profiles,
changed bundles and cross-Project reuse require explicit repair or migration.

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
./bootstrap.sh --mode full --plan
sudo ./bootstrap.sh --mode full
```

Use `--with-ai-stack` only when Ponytail, Langfuse, Honcho, Hindsight, TigerVNC, Crawl4AI and Parakeet are all desired on this Host. Parakeet and Hermes voice/messaging support are already installed by the default bootstrap unless `--skip-voice` is explicit. Do not use `--yes` until the generated plan has been inspected. Bootstrap installs pinned binaries but never authenticates GitHub, Vercel, Convex, Clerk, Stripe, Composio, Codex, Hermes providers or messaging platforms on the operator's behalf. Codex must guide the first Tailscale and Discord enrollment through their native secure flows; afterward it should prefer Station's one-time Tailnet setup buttons. The human owner retains OAuth consent, secret entry and production/destructive approval.

The current guided broker writes Zone-base credentials; it does not automatically
enroll every named Director. Never copy credentials across profiles to bypass this
boundary. `station setup --json` describes ordered actions without executing them;
`--probe` only observes the selected user service. Preserve the distinction between
local Doctor evidence and a fresh, authorized, bidirectional live mission.
