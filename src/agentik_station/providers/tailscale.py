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
    if not isinstance(payload, dict):
        return {"state":"DEGRADED","verified":False,"next_repair_action":"Tailscale status must be a JSON object."}
    self_node=payload.get("Self") or {}
    if (payload.get("BackendState") != "Running" or not isinstance(self_node, dict)
            or self_node.get("Online") is not True or not isinstance(self_node.get("TailscaleIPs"), list)
            or not self_node["TailscaleIPs"]):
        return {"state":"DEGRADED","binary":binary,"verified":False,"online":False,
                "next_repair_action":"Enroll/start Tailscale and verify local node online state before peer/ACL readback."}
    return {"state":"VERIFIED","binary":binary,"verified":True,"dns_name":self_node.get("DNSName"),
            "tailscale_ips":self_node["TailscaleIPs"],"online":True,"claim":"LOCAL_NODE_OBSERVED_NOT_PEER_ACL_ACCEPTED"}
