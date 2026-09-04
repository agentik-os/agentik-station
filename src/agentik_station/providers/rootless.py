from __future__ import annotations
import json, shutil
from pathlib import Path
from typing import Any

def zone_readiness(state_root: Path) -> dict[str, Any]:
    state_root=Path(state_root)
    required=[
        state_root/"home/.config/containers/storage.conf",
        state_root/"home/.config/containers/containers.conf",
        state_root/"rootless/POLICY.json",
    ]
    missing=[str(p) for p in required if not p.is_file() or p.is_symlink()]
    binary=shutil.which("podman")
    if missing:
        return {"state":"SCAFFOLDED","binary":binary,"missing":missing,"verified":False}
    policy=json.loads((state_root/"rootless/POLICY.json").read_text(encoding="utf-8"))
    return {
        "state":"CONFIGURED" if binary else "INSTALLABLE",
        "binary":binary,
        "policy":policy,
        "verified":False,
        "next_repair_action":"Run per-Zone Podman negative-isolation acceptance before OPERATIONAL.",
    }
