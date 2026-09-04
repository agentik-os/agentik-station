"""Small native Hermes entry point, also bundled into OS profile distributions."""

from .scrapegraph_tool import (
    CRAWL4AI_TOOL_SCHEMA, SCRAPEGRAPH_TOOL_SCHEMA,
    handle_crawl4ai, handle_scrapegraph, worker_available,
)


def register(ctx) -> None:
    ctx.register_tool(
        name="station_scrapegraph", toolset="web", schema=SCRAPEGRAPH_TOOL_SCHEMA,
        handler=handle_scrapegraph, check_fn=lambda: worker_available("scrapegraphai"),
        description=SCRAPEGRAPH_TOOL_SCHEMA["description"], emoji="🕷️",
    )
    ctx.register_tool(
        name="station_crawl4ai", toolset="web", schema=CRAWL4AI_TOOL_SCHEMA,
        handler=handle_crawl4ai, check_fn=lambda: worker_available("crawl4ai"),
        description=CRAWL4AI_TOOL_SCHEMA["description"], emoji="🕸️",
    )
