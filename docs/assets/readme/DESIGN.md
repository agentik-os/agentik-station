# README presentation assets

The README is the product entry point; `atlas.md`, `INSTALL.md`, `SETUP.md` and
the architecture/security contracts remain the detailed operational references.

## Design

`station-mission-control.svg` is an original, editable vector illustration:
ink background, pale typography, lime signal paths and a fixed technical grid.
The circuit maps intent → Station → Hermes → teams/tools → evidence, with an
evidence return path. It is an architecture illustration, not a UI screenshot,
live dashboard, deployment receipt or claim of operational readiness.

The composition takes broad README presentation cues from the user-selected
[Crawl4AI](https://github.com/unclecode/crawl4ai),
[Sim](https://github.com/simstudioai/sim) and
[Strix](https://github.com/usestrix/strix): a strong opening visual, useful entry
links, a short installation path and progressive disclosure. No upstream visual,
logo, screenshot or marketing copy is reused. These are design references, not
endorsements or Station dependencies merely by being listed here.

## GitHub compatibility and accessibility

- The SVG is self-contained: no JavaScript, foreign objects, remote fonts or
  embedded external images. It remains meaningful when animation is unavailable.
- Two small SVG motion signals are decorative. `prefers-reduced-motion: reduce`
  hides them; labels and the complete circuit are static. No flashing effects.
- The README supplies descriptive image alt text and an equivalent text sequence.
  The SVG also includes its own title and description.
- The image uses a fixed viewBox and a responsive README width. Its essential
  information is repeated as normal Markdown, including on narrow displays.
- Standard anchors and `details` / `summary` elements implement the expandable
  mission walkthrough. Anchor links navigate to a step; readers then expand it.
  There is no embedded app, script, autoplay video or pretend interactive console.
- The CI badge uses the actual GitHub Actions status. Community badges are static
  links, not fabricated member, star or benchmark counts.
- The Discord community invite is not enrollment into a user's private Station.

Keep new illustration assets in this directory, not among runtime resources.
After edits, validate local links, SVG XML and accessibility properties; inspect
the rendered asset; run relevant contract tests and `./station doctor --repo`.
Regenerate release metadata with `scripts/generate_release_metadata.py` before
the final manifest/Doctor checks. Preview files must stay outside the release tree.
