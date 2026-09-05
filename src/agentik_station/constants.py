from __future__ import annotations

from pathlib import Path

PRODUCT_VERSION = "11.34"
BLUEPRINT_VERSION = 11
SPEC_SCHEMA_VERSION = 1

CATEGORIES = {
    "SYSTEM": "1_SYSTEM",
    "PRIVATE": "2_PRIVATE",
    "AGENTIK": "3_AGENTIK",
    "ORGANIZATIONS": "4_ORGANIZATIONS",
    "PROJECTS": "5_PROJECTS",
    "FACTORY": "6_FACTORY",
    "LAB": "7_LAB",
}

ZONE_SUBDIRS = ["projects", "os", "members", "integrations", "credentials", "evidence", "ops"]
PROJECT_SUBDIRS = [
    "repos",
    "docs",
    "knowledge",
    "resources",
    "integrations",
    "credentials",
    "workspaces",
    "worktrees",
    "state",
    "artifacts",
    "evidence",
    "ops",
]
ZONE_STATE_SUBDIRS = ["home", "hermes", "mission-state", "databases", "connector-state", "caches", "projects"]

SYSTEM_PACKAGES = [
    "git",
    "curl",
    "ca-certificates",
    "python3",
    "python3-venv",
    "python3-yaml",
    "python3-pip",
    "jq",
    "unzip",
    "rsync",
    "acl",
    "sqlite3",
    "fail2ban",
    "ufw",
    "podman",
    "uidmap",
    "slirp4netns",
    "fuse-overlayfs",
    "ffmpeg",
    "libopus0",
    "portaudio19-dev",
]

MATURITY_STATES = [
    "SPECIFIED",
    "SCAFFOLDED",
    "INSTALLABLE",
    "CONFIGURED",
    "VERIFIED",
    "OPERATIONAL",
    "DEGRADED",
]

REPO_EXCLUDES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".DS_Store",
}

TEXT_EXTENSIONS = {".md", ".yaml", ".yml", ".json", ".py", ".sh", ".toml", ".txt", ""}

LIVE_ROOTS = {
    "config": Path("/etc/station"),
    "software": Path("/opt/station"),
    "runtime": Path("/srv/station"),
    "varlib": Path("/var/lib/station"),
    "log": Path("/var/log/station"),
    "backups": Path("/var/backups/station"),
    "run": Path("/run/station"),
    "systemd": Path("/etc/systemd/system"),
    "bin": Path("/usr/local/bin"),
}
