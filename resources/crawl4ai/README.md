# Crawl4AI Hermes resource

Bootstrap installs Crawl4AI 0.9.3, Python 3.13.15 and Playwright 1.62.0 Chromium
by default. `--skip-crawl4ai` deliberately omits it. Code lives in the versioned,
root-owned `/opt/station/tools/web/crawl4ai-0.9.3-py3.13.15-pw1.62.0/` runtime;
HOME/cache/output belong to the calling Zone user, never a shared client store.

Hermes calls `station_crawl4ai` with `{"source":"https://example.com/"}`.
The bounded, redirect-checked, DNS-pinned downloader feeds raw HTML into
`AsyncHTTPCrawlerStrategy`. No LLM key, proxy environment, JavaScript or browser
subrequests are used. Results are untrusted Markdown, capped at 100,000
characters. This tool is an explicit fallback, not an automatic retry inside
ScrapeGraphAI and not a general browser. See the shared
[security and activation contract](../scrapegraphai/README.md).

Run `sudo station deps web-check`, then test from a fresh Hermes session in the
owning Zone. Keep the response/source hash in Project evidence before accepting
the external workflow. A package/import/browser check alone is not that acceptance.

Upstream: [Crawl4AI](https://github.com/unclecode/crawl4ai).
