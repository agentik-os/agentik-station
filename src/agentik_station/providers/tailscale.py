from __future__ import annotations
import json, shutil, subprocess
from typing import Any

def status() -> dict[str, Any]:
    binary = shutil.which("tailscale")
    if not binary:
        return {"state":"NOT_INSTALLED","binary":None,"verified":False}
    completed = subprocess.run([binary,"status","--json"],capture_output=True,text=True,check=False,timeout=30)
    if completed.returncode != 0:
        return {"state":"DEGRADED","binary":binary,"verified":False,"stderr":completed.stderr[-2000:],
                "next_repair_action":"Repair Tailscale enrollment before remote Fleet operations."}
    try:
        payload=json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"state":"DEGRADED","binary":binary,"verified":False,"next_repair_action":"Tailscale returned invalid JSON."}
    self_node=payload.get("Self") or {}
    return {"state":"VERIFIED","binary":binary,"verified":True,"dns_name":self_node.get("DNSName"),
            "tailscale_ips":self_node.get("TailscaleIPs",[]),"online":self_node.get("Online",True)}
