#!/usr/bin/env python3
"""Internal bootstrap state entry point; uses distribution Python/stdlib only."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentik_station.bootstrap_state import main

if __name__ == "__main__":
    raise SystemExit(main())
