import json
from types import SimpleNamespace

import pytest

from agentik_station.providers import tailscale


@pytest.mark.parametrize("payload,verified", [
    ({"BackendState": "NeedsLogin"}, False),
    ({"BackendState": "Stopped", "Self": {"Online": True, "TailscaleIPs": ["100.64.0.1"]}}, False),
    ({"BackendState": "Running", "Self": {"Online": False, "TailscaleIPs": ["100.64.0.1"]}}, False),
    ({"BackendState": "Running", "Self": {}}, False),
    ([], False),
    ({"BackendState": "Running", "Self": {"Online": True, "TailscaleIPs": ["100.64.0.1"]}}, True),
])
def test_zero_exit_is_not_tailscale_enrollment(monkeypatch, payload, verified):
    monkeypatch.setattr(tailscale.shutil, "which", lambda name: "/usr/bin/tailscale")
    monkeypatch.setattr(tailscale.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(payload)))
    assert tailscale.status()["verified"] is verified
