#!/usr/bin/env python3
"""Deterministic Librarian/Builder handoff utilities.

This program does not perform research itself. Research is executed by the
Librarian OS through its Hermes profile, skills, source adapters, and research
fabric. The deterministic helper owns packet scaffolding, command discovery,
and release-gate validation only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MANDATORY_LANES = ["topic_map", "book_deep", "bestseller", "web_deep"]
UNIVERSAL_LANES = [
    "topic_map",
    "book_deep",
    "bestseller",
    "web_deep",
    "experts",
    "canonical",
    "latest",
    "papers",
    "docs",
    "github",
    "community",
    "contrarian",
    "triangulate",
    "factcheck",
    "knowledge_gap",
]
COMMANDS = [
    "/research",
    "/book",
    "/bestseller",
    "/web-deep",
    "/experts",
    "/prior",
    "/prior-verify",
    "/discover",
    "/canonical",
    "/latest",
    "/papers",
    "/docs",
    "/github",
    "/community",
    "/contrarian",
    "/sources",
    "/verify-source",
    "/principles",
    "/contradictions",
    "/triangulate",
    "/factcheck",
    "/knowledge-gap",
    "/refresh-knowledge",
    "/best-inputs",
    "/handoff",
    "/research-to-os",
]


def init(theme: str, out: str) -> None:
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        "# 14_BUILDER_HANDOFF\n\nSTATUS: INCOMPLETE\n\n",
        f"## Research mission\n- Theme: {theme}\n- Target OS:\n- Mission:\n- Librarian run ID:\n\n",
        "## Research lanes\n"
        "- Topic Map:\n- Book Deep:\n- Bestseller discovery/editorial synthesis:\n"
        "- Web Deep:\n- Expert/Operator Map:\n- Canonical sources:\n- Current/latest:\n"
        "- Scholar/papers:\n- Official docs:\n- GitHub/engineering evidence:\n"
        "- Community/practitioner evidence:\n- Contrarian/Failure:\n- Triangulation/Factcheck:\n\n",
        "## Source integrity\n- Sources discovered:\n- Sources verified:\n- Freshness boundary:\n"
        "- Independence boundary:\n- Known gaps:\n- Contradictions:\n\n",
        "## 15 best inputs\n",
    ]
    for i in range(1, 16):
        parts.append(
            f"\n### Input {i:02d}\n- Principle:\n- Source IDs:\n- Research lane(s):\n"
            "- Why it matters:\n- Skill implication:\n- Program implication:\n"
            "- Workflow/automation implication:\n- Eval:\n- Doctor probe:\n"
            "- Recovery implication:\n- Confidence/caveat:\n"
        )
    parts.append(
        "\n## Contradictions / trade-offs\n\n## Recommended OS architecture changes\n\n"
        "## Open questions\n\n## Traceability table\n"
    )
    p.write_text("".join(parts), encoding="utf-8")
    print(p)


def validate(packet: str) -> int:
    data = json.loads(Path(packet).read_text(encoding="utf-8"))
    errs: list[str] = []
    lanes = data.get("lanes", {})
    for lane in MANDATORY_LANES:
        if lane not in lanes:
            errs.append(f"missing required research lane: {lane}")
    sources = data.get("sources", [])
    inputs = data.get("selected_inputs", [])
    if len(inputs) != 15:
        errs.append(f"selected_inputs must contain exactly 15 items, got {len(inputs)}")
    src_ids = {s.get("source_id") for s in sources if s.get("source_id")}
    for i, source in enumerate(sources, 1):
        for key in ["source_id", "title", "source_type", "verification_status", "principles"]:
            if not source.get(key):
                errs.append(f"source {i} missing {key}")
    for i, item in enumerate(inputs, 1):
        for key in ["input_id", "principle", "source_ids", "os_mapping", "eval", "doctor_probe", "recovery_implication"]:
            if not item.get(key):
                errs.append(f"input {i} missing {key}")
        unknown = set(item.get("source_ids", [])) - src_ids
        if unknown:
            errs.append(f"input {i} references unknown sources: {sorted(unknown)}")
    print("LIBRARIAN VALIDATOR V3")
    for err in errs:
        print("FAIL:", err)
    if not errs:
        print("PASS")
    return 1 if errs else 0


def catalog(as_json: bool) -> None:
    payload = {
        "librarian_os": "3.0.0",
        "doctrine": "LLM prior -> hypothesis -> research -> verification -> synthesis -> durable knowledge",
        "commands": COMMANDS,
        "mandatory_builder_lanes": MANDATORY_LANES,
        "universal_research_lanes": UNIVERSAL_LANES,
        "bestseller_semantics": {
            "/bestseller": "discover and curate influential/canonical works with evidence labels",
            "/book --bestseller": "create an original editorial/pedagogical synthesis; never reproduce protected works",
        },
    }
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print("Librarian OS 3.0.0 — Universal Knowledge")
    print("Commands:", " ".join(COMMANDS))
    print("Mandatory Builder lanes:", ", ".join(MANDATORY_LANES))


def main() -> None:
    ap = argparse.ArgumentParser(prog="librarian")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init", help="Create a Builder handoff scaffold")
    p.add_argument("--theme", required=True)
    p.add_argument("--output", required=True)
    p = sp.add_parser("validate", help="Validate a research packet before Builder handoff")
    p.add_argument("packet")
    p = sp.add_parser("catalog", help="Show the Librarian v3 research/command surface")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd == "init":
        init(args.theme, args.output)
    elif args.cmd == "validate":
        raise SystemExit(validate(args.packet))
    else:
        catalog(args.json)


if __name__ == "__main__":
    main()
