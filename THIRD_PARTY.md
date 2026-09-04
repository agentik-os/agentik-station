# Third-Party Software

Station integrates with external projects rather than relicensing them. Before distribution or production deployment, retain and review each pinned upstream license, notices and service terms. Key integrations include:

- [NousResearch Hermes Agent](https://github.com/NousResearch/hermes-agent) — MIT
- [DietrichGebert Ponytail](https://github.com/DietrichGebert/ponytail) — MIT
- [Langfuse](https://github.com/langfuse/langfuse) — review the notices for the selected FOSS/EE deployment
- [Plastic Labs Honcho](https://github.com/plastic-labs/honcho) — AGPL-3.0
- [Vectorize Hindsight](https://github.com/vectorize-io/hindsight) — review repository/component licenses for the selected deployment
- [TigerVNC](https://github.com/TigerVNC/tigervnc) — GPL-2.0
- [Crawl4AI](https://github.com/unclecode/crawl4ai) — Apache-2.0
- [achetronic Parakeet](https://github.com/achetronic/parakeet) — MIT
- [Python](https://www.python.org/), [uv](https://github.com/astral-sh/uv), [Node.js](https://nodejs.org/) and npm
- [GitHub CLI](https://github.com/cli/cli) — MIT
- [Vercel CLI](https://github.com/vercel/vercel) — Apache-2.0
- [OpenAI Codex CLI](https://github.com/openai/codex) — Apache-2.0
- [Composio CLI](https://github.com/ComposioHQ/composio) — MIT
- [Tailscale](https://github.com/tailscale/tailscale) — BSD-3-Clause
- Podman and its runtime dependencies
- Restic

Exact reviewed versions are recorded in `config/versions.lock`. The Station repository must not copy third-party credentials, bundle upstream code without its notices, or imply ownership of these projects.
