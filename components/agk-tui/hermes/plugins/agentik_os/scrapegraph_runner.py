"""Stdin/stdout worker for both installed web extraction libraries."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib.metadata
import json
import logging
import os
import sys
from pathlib import Path


from web_fetch import fetch_html
from web_runtime import PLAYWRIGHT_VERSION, VERSIONS


def check_tokenizers() -> None:
    # A deployed worker must not silently fetch its tokenizer on the first job.
    cache = os.environ.get("TIKTOKEN_CACHE_DIR")
    if not cache:
        return  # Development/CI may use tiktoken's standard prewarmed cache.
    assets = {
        "o200k_base": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
        "cl100k_base": "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    }
    for name, digest in assets.items():
        url = f"https://openaipublic.blob.core.windows.net/encodings/{name}.tiktoken"
        path = Path(cache) / hashlib.sha1(url.encode()).hexdigest()
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Missing/corrupt tokenizer asset; rebuild the reviewed ScrapeGraphAI runtime")


async def crawl_html(html: str, source: str) -> str:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
    from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

    async with AsyncWebCrawler(crawler_strategy=AsyncHTTPCrawlerStrategy(), config=BrowserConfig(verbose=False)) as crawler:
        result = await crawler.arun(
            url="raw:<html>" + html + "</html>",
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, base_url=source, verbose=False),
        )
        if not result.success:
            raise ValueError("Crawl4AI extraction failed")
        return str(result.markdown.raw_markdown)[:100000]


def extract(request: dict) -> dict:
    component = request["component"]
    if importlib.metadata.version(component) != VERSIONS[component]:
        raise ValueError("installed package differs from the reviewed pin")
    if component == "scrapegraphai":
        check_tokenizers()
    if request.get("health"):
        if importlib.metadata.version("playwright") != PLAYWRIGHT_VERSION:
            raise ValueError("Playwright version differs from the reviewed pin")
        if component == "crawl4ai":
            from crawl4ai import AsyncWebCrawler  # noqa: F401
        else:
            from scrapegraphai.graphs import SmartScraperGraph  # noqa: F401
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        return {"success": True, "component": component, "version": VERSIONS[component], "browser": "launch-passed", "claim": "INSTALLED_NOT_EXTERNAL_ACCEPTED"}
    html, final_source = fetch_html(request["source"])
    if component == "crawl4ai":
        return {"success": True, "markdown": asyncio.run(crawl_html(html, final_source))}
    from scrapegraphai.graphs import SmartScraperGraph
    key = os.environ.get("SCRAPEGRAPHAI_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Zone-local OpenAI credential is missing")
    graph = SmartScraperGraph(
        prompt=request["prompt"],
        source="<html>" + html + "</html>",
        config={"llm": {"api_key": key, "model": request["model"], "max_tokens": 4096}, "verbose": False, "headless": True},
    )
    return {"success": True, "data": graph.run()}


def main() -> int:
    os.environ["SCRAPEGRAPHAI_TELEMETRY_ENABLED"] = "false"
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.read(8193))
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            payload = extract(request)
        output = json.dumps(payload, ensure_ascii=True)
        if len(output) > 512000:
            raise ValueError("extraction output too large")
        print(output)
        return 0
    except Exception:
        # Provider exceptions can contain request bodies or credentials.
        print('{"success":false,"error":"Extraction failed; check runtime health, public URL and Zone credential."}')
        return 1


if __name__ == "__main__":
    # Bound native writes without breaking tokenizer/browser cache files (>1 MiB).
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    raise SystemExit(main())
