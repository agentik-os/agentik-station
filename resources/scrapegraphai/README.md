# ScrapeGraphAI Hermes resource

This resource is installed by `station_deps_install.sh` into the owning Zone's
isolated Python 3.13 environment with `scrapegraphai==2.2.2` and
`playwright==1.62.0`; Chromium is installed by the same idempotent action.

Hermes exposes it as `station_scrapegraph`. The tool accepts only bounded
HTTP(S) URLs, rejects private/reserved addresses and embedded credentials, and
executes the worker without putting provider keys in arguments, logs or
evidence. It is a research/extraction capability, not a general-purpose
browser or a second messaging gateway.

The owning Zone must provide `SCRAPEGRAPHAI_OPENAI_API_KEY` or
`OPENAI_API_KEY` in its credential environment when an OpenAI model is chosen.
No key is bundled in this resource.
