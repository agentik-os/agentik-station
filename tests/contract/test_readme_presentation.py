"""Offline contracts for the GitHub README's navigation and illustration."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"


def _anchors(text: str) -> set[str]:
    # Covers this README's plain-text headings and explicit mission anchors.
    headings = re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)
    return {
        re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        for heading in headings
    } | set(re.findall(r'<a\s+(?:id|name)="([^"]+)"', text))


def test_readme_local_links_and_fragments_resolve() -> None:
    text = re.sub(r"```.*?```", "", README.read_text(), flags=re.DOTALL)
    links = re.findall(r"\]\(([^)]+)\)", text)
    links += re.findall(r'(?:href|src)="([^"]+)"', text)
    assert links
    for link in links:
        target = urlsplit(html.unescape(link))
        if target.scheme or target.netloc:
            assert target.scheme == "https", link
            continue
        path = ROOT / unquote(target.path) if target.path else README
        assert path.is_file(), link
        if target.fragment:
            assert unquote(target.fragment) in _anchors(path.read_text()), link


def test_readme_has_accessible_progressive_disclosure() -> None:
    text = README.read_text()
    sections = text.count("<details>")
    assert sections >= 7
    assert text.count("</details>") == sections
    assert text.count("<summary>") == text.count("</summary>") == sections
    for image in re.findall(r"<img\b[^>]*>", text):
        assert re.search(r'alt="[^"]+"', image), image
    assert "https://discord.gg/agentik-os" in text
    assert "not a live status display" in text
    assert "READY_FOR_SETUP" in text
    assert "LICENSE.md" in text


@pytest.mark.parametrize("name", [
    "station-mission-control", "station-system-map", "station-install-flow",
    "station-os-map", "station-chat-map", "station-filesystem-map",
    "station-evidence-loop",
])
def test_readme_svg_is_self_contained_and_motion_optional(name: str) -> None:
    path = ROOT / f"docs/assets/readme/{name}.svg"
    assert str(path.relative_to(ROOT)) in README.read_text()
    assert path.stat().st_size < 20_000
    root = ET.fromstring(path.read_text())
    tags = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}
    assert {"title", "desc", "animateMotion"} <= tags
    assert not {"script", "foreignObject", "image", "iframe"} & tags
    if name == "station-mission-control":
        assert root.attrib["viewBox"] == "0 0 1280 700"
    else:
        _, _, width, height = map(float, root.attrib["viewBox"].split())
        assert width == 800 and height >= width
    assert root.attrib["role"] == "img"
    ids = {element.attrib.get("id") for element in root.iter()}
    assert set(root.attrib["aria-labelledby"].split()) <= ids
    for element in root.iter():
        for key, value in element.attrib.items():
            assert not key.lower().startswith("on"), key
            assert not key.endswith("href"), value
        if element.tag.rsplit("}", 1)[-1] in {"animateMotion", "animate"}:
            assert element.attrib.get("repeatCount", "1") == "1"
            assert 0 < float(element.attrib["dur"].removesuffix("s")) <= 5
    style = "".join(root.itertext())
    assert "prefers-reduced-motion: reduce" in style
    assert ".motion { display: none; }" in style
    assert "@import" not in style
    assert "not live telemetry" in style or "not live status" in style.lower()


def test_readme_preserves_system_explanation_and_readiness_boundaries() -> None:
    text = README.read_text()
    assert {
        "the-whole-system", "quickstart", "operative-systems", "the-toolchain",
        "discord-is-the-cockpit", "clean-by-construction",
        "readiness-without-the-fine-print",
    } <= _anchors(text)
    assert "./bootstrap.sh --mode full --with-ai-stack --plan" in text
    assert "Current activation limits" in text
    assert "Zone-scoped profile names" in text
    assert "not automatically the intended OS Director" in text
    assert "Project repository" in text
