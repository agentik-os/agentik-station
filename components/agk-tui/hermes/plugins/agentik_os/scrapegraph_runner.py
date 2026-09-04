"""Small stdin/stdout worker kept outside Hermes' Python environment."""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    request = json.load(sys.stdin)
    from scrapegraphai.graphs import SmartScraperGraph

    model = request["model"]
    llm = {"model": model, "format": "json"}
    if model.startswith("openai/"):
        key = os.environ.get("SCRAPEGRAPHAI_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("Zone-local OpenAI key is required for an OpenAI ScrapeGraphAI model")
        llm["api_key"] = key
    graph = SmartScraperGraph(
        prompt=request["prompt"],
        source=request["source"],
        config={"llm": llm, "verbose": False, "headless": True},
    )
    print(json.dumps({"success": True, "data": graph.run()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
