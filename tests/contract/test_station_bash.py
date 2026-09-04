from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_spec_command_uses_generic_defaults() -> None:
    result = subprocess.run(
        [str(ROOT / "station"), "spec"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["host_id"] == "station-core-01"
    assert payload["role"] == "core"
    assert payload["release_version"] == "11.12"


def test_bash_wrapper_is_thin_and_avoids_unsafe_shell_patterns() -> None:
    text = (ROOT / "station.sh").read_text(encoding="utf-8")
    assert '"$STATION" spec' in text
    assert '"$STATION" plan --spec "$spec"' in text
    assert 'sudo "$STATION" apply --spec "$spec"' in text
    assert "eval " not in text
    assert ("shell" + "=" + "True") not in text
    assert ("curl" + " |") not in text
