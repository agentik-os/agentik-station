# Station toolchain and required full Host AI stack

[`config/versions.lock`](../../config/versions.lock) is the machine-readable pin set. [`config/deps/stack.yaml`](../../config/deps/stack.yaml) describes role and maturity. Pins were checked against upstream releases on 2026-09-04.

> **Observed installation blocker (2026-09-05):** native Hermes scanning blocks
> the pinned Ponytail source. `--all` now continues independent component
> installers and returns an aggregate **INCOMPLETE/nonzero** result; it does not
> silently skip or bypass the decision. Ponytail remains
> `NOT_INSTALLED` until the [upstream/security gate is resolved](../audit/2026-09-05-ponytail-native-scan.md).

## Default operator toolchain

The complete Linux AMD64 Host software stack is the default in 11.28; the old
`--with-ai-stack` flag is an alias. `--minimal` declares a partial installation.
Start with [`FULL_STACK.md`](FULL_STACK.md) and `station deps full-plan` for the
exhaustive inventory, including server application images and native Hermes
client libraries. `sudo station deps full-check` checks actual software and
keeps configuration/account acceptance separate.

`bootstrap.sh` installs these under the dedicated `agk-station` account:

Station then publishes only the allowlisted executable/package/runtime code to
root-owned, versioned `/opt/station/tools/toolchain` and exposes checked launchers
in `/usr/local/bin`. This gives Zone profiles executable access without access to
the private operator home. Their own `HOME`, credentials and configuration remain
unchanged. The discord.js resource below remains an isolated operator resource;
Project applications declare/install their own SDK dependency.

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
| ScrapeGraphAI | 2.2.2 + Playwright Chromium 1.62.0 | default versioned read-only Python 3.13 runtime; `station_scrapegraph` uses a Zone OpenAI key |
| Crawl4AI | 0.9.3 + Playwright Chromium 1.62.0 | default versioned read-only Python 3.13 runtime; `station_crawl4ai` requires no LLM key |
| shadcn CLI | 4.21.0 | pinned npm package + locked registry integrity; components remain Project-owned source |
| ChatbotX CLI | 0.1.3 | default isolated package + exact executable SHA256 + Node wrapper; private account-free version/help verification; [connection and MCP limits](../../resources/chatbotx/README.md) |
| Hermes Agent | v2026.8.31 / reviewed commit | checksum-locked upstream installer executed as `agk-station`, shared launcher, isolated Zone homes |
| Hermes voice | explicit `voice,messaging` extras | OpenAI `gpt-transcribe` primary STT; OpenAI `gpt-4o-mini-tts` / `alloy`; Zone-local credential |
| Tailscale | minimum reviewed 1.102.3, stable track | signed Ubuntu/Debian repository with checksum-locked archive key; normal stable apt upgrade path |

```bash
station deps toolchain-plan
sudo station deps toolchain-install
station deps toolchain-check
sudo station deps web-check
```

Installation is not authentication. Complete each native account flow only for
the principal that needs it; use Station's model-only setup route instead of
substituting the full Hermes wizard. For Discord tools, inspect
`station provider composio-discord plan --zone <zone-id>`. Its current link/verify
facade cannot establish a trusted developer project/workdir binding and refuses
before account execution. See [the exact missing binding](COMPOSIO_DEVELOPER_BINDING.md).
The intended Composio account is an adapter behind Hermes, not another bot Gateway.

## Project resource recipe

`resources/CATALOG.json` records the preferred, open `web-product` baseline: Next.js, React, Convex, Clerk, Stripe, Tailwind CSS, shadcn/ui and Lucide. Inspect the exact pinned plan before changing an owning Project repository:

```bash
station resource list
station resource stack-plan --id web-product
```

The recipe does not create provider accounts, write secrets or force this stack on Projects with a different declared contract.

Both web runtimes live under `/opt/station/tools/web/<component>-<version>-py<version>-pw<version>/`; state and secrets stay under the calling Zone identity. Their automatic adapters process guarded public HTML, without JavaScript/browser subrequests. Chromium launch is checked separately. OS compilation includes the small native `station-web` plugin; existing profiles require reinstall/config activation and fresh-session acceptance. See [limits and verification](../../resources/scrapegraphai/README.md).

## Required full Host components

These projects are not interchangeable Python dependencies:

| Component | Pin | Station action | Still required before OPERATIONAL |
|---|---:|---|---|
| Strix | 1.6.1 / wheel and image digests | isolated CLI, existing Hermes DevOps team, typed local-source adapter | disposable LAB/network acceptance, reviewed source disclosure, dedicated model key, human grant and independent findings verification |
| Ponytail | v4.9.0 / immutable commit | blocked before activation by the retained native full-tree rejection; no account scanner opt-out can override it | new source/security acceptance, then coding-session acceptance |
| Langfuse | server v4.28.1; native SDK 4.15.1 | complete six-image server bundle, source and Hermes client | private service, secrets, trace readback, backup |
| Honcho | SDK 2.4.0; Hermes client 2.2.0 | isolated operator client, native Hermes client and complete server image bundle | API/self-host, Zone credentials, memory round-trip |
| Hindsight | client 0.9.2; Hermes client 0.6.1 | isolated operator client, native Hermes client and complete server image bundle | one active external memory provider per profile; enrollment + Zone-isolation/recall test |
| ChatbotX | app 1.5.0; CLI 0.1.3 | CLI plus complete nine-image app/MCP/infrastructure bundle | private deployment, secrets, no demo seed; owning workspace and MCP/API readback |
| TigerVNC | distro package; upstream v1.16.2 reviewed | `apt` package install | private-network binding, auth, firewall and viewer readback |
| Parakeet | v0.8.0 / immutable image digest | shared loopback-only, read-only int8 container and explicit native Hermes voice provider | health + synthetic/Discord voice attachment readback; shared loopback is not a cross-Zone access boundary |

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

It installs all required software through independent installers but does not
invent secrets, start new database-backed applications, expose VNC, or mark
external services accepted. Inspect exact image digests and activation gates in
[`resources/services`](../../resources/services). Ponytail's current security
block prevents full-success acceptance, even when the other installers pass.

Strix adds no automatic scans or Docker permissions; its subordinate team and
authorization contract are in the [security resource guide](../../resources/strix/README.md).
Fresh ScrapeGraphAI installs prefetch and verify tokenizer assets in the read-only
runtime. `web-check` refuses missing/corrupt deployed assets. An older same-version
runtime without `tokenizers/` must be inspected and archived by an operator, then
rebuilt; the installer does not silently overwrite an existing published runtime.

## Hermes update policy

```bash
station hermes check
station update plan
station update check
sudo station deps enable-auto-update
```

The bootstrap-enabled weekly timer now performs coupled dependency discovery
without changing Hermes. `--skip-hermes-auto-update` opts out. Registry/source
observations never authorize new pins: review the SDKs, adapters, image digests,
state migrations and native tests before deploying a new Station release.
`station hermes update` reports that coordinated-release requirement instead of
pulling an independent HEAD. See [update and recovery gates](../operations/COORDINATED_UPDATES.md).

Upstream references: [Hermes updating](https://hermes-agent.nousresearch.com/docs/getting-started/updating), [Codex CLI](https://developers.openai.com/codex/cli), [Composio CLI](https://docs.composio.dev/docs/cli), [Vercel CLI](https://vercel.com/docs/cli), [GitHub CLI](https://cli.github.com/manual/).

Voice and bot-guided setup: [`VOICE_AND_GUIDED_SETUP.md`](VOICE_AND_GUIDED_SETUP.md).
