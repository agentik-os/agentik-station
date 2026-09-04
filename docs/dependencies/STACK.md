# Station toolchain and optional AI stack

[`config/versions.lock`](../../config/versions.lock) is the machine-readable pin set. [`config/deps/stack.yaml`](../../config/deps/stack.yaml) describes role and maturity. Pins were checked against upstream releases on 2026-09-04.

## Default operator toolchain

`bootstrap.sh` installs these under the dedicated `agk-station` account:

| Tool | Pin | Installation/verification |
|---|---:|---|
| Python | 3.14.7 | installed by pinned `uv` as `python-latest`; does not replace system Python |
| Python AI | 3.13.15 | installed by pinned `uv` as `python-ai`; isolated SDK/tool compatibility runtime |
| Hermes Python | 3.11 | Hermes-managed venv; upstream currently requires `<3.14` |
| Node.js | 24.20.0 LTS | official archive + published SHA-256 |
| npm | 12.0.2 | pinned npm registry package |
| GitHub CLI | 2.100.0 | official release archive + published SHA-256 |
| Vercel CLI | 59.11.2 | pinned npm package + locked registry integrity |
| Codex CLI | 0.153.2 | pinned npm package + locked registry integrity |
| Composio CLI | 0.4.0 | checksum-locked official installer + verified bundle, pinned release, no automatic login/plugin setup |
| discord.js SDK | 14.27.0 | npm lock + registry integrity, isolated under `.local/share/station-sdk/discord-js`; never starts a Gateway |
| ScrapeGraphAI | 2.2.2 + Playwright Chromium 1.62.0 | default isolated Python 3.13 venv and Hermes `station_scrapegraph` tool | Zone model credential, public URL extraction and evidence readback |
| shadcn CLI | 4.21.0 | pinned npm package + locked registry integrity; components remain Project-owned source |
| Hermes Agent | v2026.8.31 / reviewed commit | checksum-locked upstream installer executed as `agk-station`, shared launcher, isolated Zone homes |
| Hermes voice | explicit `voice,messaging` extras | OpenAI `gpt-transcribe` primary STT; OpenAI `gpt-4o-mini-tts` / `alloy`; Zone-local credential |
| Tailscale | minimum reviewed 1.102.3, stable track | signed Ubuntu/Debian repository with checksum-locked archive key; normal stable apt upgrade path |

```bash
station deps toolchain-plan
sudo station deps toolchain-install
station deps toolchain-check
```

Installation is not authentication. Complete `gh auth login`, `vercel login`, `composio login`, Codex sign-in and `hermes setup` only for the principals that need them. For Discord tools, use `station provider composio-discord plan|link|verify --zone <zone-id>`; the selected Composio account is an adapter behind Hermes, not another bot Gateway.

## Project resource recipe

`resources/CATALOG.json` records the preferred, open `web-product` baseline: Next.js, React, Convex, Clerk, Stripe, Tailwind CSS, shadcn/ui and Lucide. Inspect the exact pinned plan before changing an owning Project repository:

```bash
station resource list
station resource stack-plan --id web-product
```

The recipe does not create provider accounts, write secrets or force this stack on Projects with a different declared contract.

## Optional components

These projects are not interchangeable Python dependencies:

| Component | Pin | Station action | Still required before OPERATIONAL |
|---|---:|---|---|
| Ponytail | v4.9.0 / immutable commit | native `hermes plugins install ... --ref <sha> --enable` | plugin review + coding-session acceptance |
| Langfuse | v4.28.1 | immutable tagged source checkout | secrets, compose/Kubernetes deployment, trace readback, backup |
| Honcho | SDK 2.4.0 | isolated Python 3.13 venv | API/self-host, Zone credentials, memory round-trip |
| Hindsight | client 0.9.2 | isolated Python 3.13 client; Hermes uses native `hermes memory setup` | provider enrollment + Zone-isolation/recall test |
| TigerVNC | distro package; upstream v1.16.2 reviewed | `apt` package install | private-network binding, auth, firewall and viewer readback |
| Crawl4AI | 0.9.3 | isolated Python 3.13 `uv tool`, browser setup and upstream Doctor | Hermes tool allowlist and egress policy |
| Parakeet | v0.8.0 / immutable image digest | loopback-only, read-only int8 container and Hermes command-STT adapter | health + synthetic/Discord fallback transcription readback |

```bash
station deps list
sudo station deps install --component ponytail
sudo station deps install --component hindsight
sudo station deps install --component crawl4ai
sudo station deps install --all
```

The one-command equivalent on a fresh Host is:

```bash
sudo ./bootstrap.sh --mode full --with-ai-stack
```

It stages the complete optional stack but does not invent secrets, start Langfuse, expose VNC, or mark external services accepted.

## Hermes update policy

```bash
station hermes check
station hermes update
sudo station deps enable-auto-update
```

The update wrapper requests a pre-update backup, runs Hermes Doctor, observes the gateway, stores a receipt in `$HERMES_HOME/station-update-receipts`, and exits non-zero on failed validation. Bootstrap enables the weekly timer by default; `--skip-hermes-auto-update` opts out. If Doctor fails, Station asks Hermes to restore the `pre-update` state and reports that code compatibility still needs review.

Upstream references: [Hermes updating](https://hermes-agent.nousresearch.com/docs/getting-started/updating), [Codex CLI](https://developers.openai.com/codex/cli), [Composio CLI](https://docs.composio.dev/docs/cli), [Vercel CLI](https://vercel.com/docs/cli), [GitHub CLI](https://cli.github.com/manual/).

Voice and bot-guided setup: [`VOICE_AND_GUIDED_SETUP.md`](VOICE_AND_GUIDED_SETUP.md).
