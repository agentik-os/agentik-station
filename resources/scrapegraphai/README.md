# ScrapeGraphAI Hermes resource

Bootstrap installs `scrapegraphai==2.2.2` and `playwright==1.62.0` with Chromium
in `/opt/station/tools/web/scrapegraphai-2.2.2-py3.13.15-pw1.62.0/`.
Software is root-owned/read-only after installation; each worker runs as its
owning Zone identity with that user's HOME, cache and credential environment.
Hermes's Python 3.11 environment does not import these Python 3.13 dependencies.

`station_scrapegraph` accepts a public HTTP(S) `source`, an extraction `prompt`
and an optional `openai/model`. The Zone supplies `SCRAPEGRAPHAI_OPENAI_API_KEY`
or `OPENAI_API_KEY`; no credential is bundled. Only that selected key reaches
the worker, never other chat/provider keys, proxy settings or CLI arguments.

The adapter validates DNS and pins the connection to a public IP for every
redirect. It fetches at most 2 MiB and passes HTML, not a navigable URL, to the
library. JavaScript and browser subrequests are disabled in this adapter;
Chromium is installed and launch-tested for separately governed browser use.
Extraction times out after 180 seconds. Library logs/errors are suppressed.
Output remains **untrusted page/LLM data**, not instructions or permission to act.

`station_crawl4ai` is the explicit no-LLM Markdown fallback. Hermes chooses it
when appropriate; the ScrapeGraphAI handler does not silently change tools.

`sudo station deps web-check` verifies both imports, pins and Chromium launch.
The operator plugin and newly compiled OS profiles include the tools in the
native `web` toolset. Existing profiles need recompilation/reinstallation;
Hermes preserves existing user config, so enable `station-web` there explicitly
if needed. Run plugin Doctor and a fresh-session test in the owning Zone.
Record the source hash and outcome in the Project evidence store; the returned
hash is not itself a durable receipt or external acceptance.

An interrupted package installation without a root-owned `BUILT` marker fails
closed on retry. Inspect and archive only the reported version directory before
reinstalling. An already published runtime is not overwritten; reruns repeat its
health check. Updating the pins creates a separate versioned runtime.

Upstream: [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai).

September 5 verification adds an actual `SmartScraperGraph.run()` test with a fake
local model and network disabled. This exercises the installed library's graph,
not only a mocked constructor; it does not prove paid-provider connectivity.
DNS resolution now occurs only inside the bounded worker. Scratch output remains
inside the Zone cache and cancellation terminates the worker process group.

Fresh installations prewarm SHA256-verified `o200k_base` and `cl100k_base` assets
under the published runtime's `tokenizers/`; health/extraction fail closed if those
deployed assets are missing/corrupt. Older immutable runtimes lacking them require
operator inspection/archive and rebuild, not a silent in-place overwrite.
