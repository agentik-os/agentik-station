from __future__ import annotations

import hashlib
import json
import os
import pwd
import grp
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .configuration import load_station_config
from .constants import CATEGORIES, PRODUCT_VERSION, TEXT_EXTENSIONS
from .filesystem import ensure_no_symlinks
from .identifiers import (
    environment_slug,
    normalize_deploy_environment,
    validate_identifier,
    validate_operation_id,
    validate_optional_identifier,
    validate_version,
)
from .identity import zone_unix_user
from .maturity import load_catalog, load_os_catalog
from .os_contract import doctor_os_source
from .models import ROLES, ZoneSpec
from .paths import LayoutPaths


@dataclass
class DoctorResult:
    scope: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def pass_check(self, name: str, detail: str | None = None) -> None:
        item: dict[str, Any] = {"name": name, "status": "PASS"}
        if detail:
            item["detail"] = detail
        self.checks.append(item)

    def fail(self, name: str, message: str, next_action: str) -> None:
        self.issues.append({"name": name, "status": "FAIL", "message": message, "next_repair_action": next_action})

    def warn(self, name: str, message: str, next_action: str | None = None) -> None:
        item: dict[str, Any] = {"name": name, "status": "WARN", "message": message}
        if next_action:
            item["next_repair_action"] = next_action
        self.warnings.append(item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "scope": self.scope,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ok": self.ok,
            "checks": self.checks,
            "issues": self.issues,
            "warnings": self.warnings,
        }


def _check_regular(result: DoctorResult, path: Path, label: str) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        result.fail(label, f"Missing required file: {path}", f"Restore {path} from the active Station release.")
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        result.fail(label, f"Required path is not a regular non-symlink file: {path}", "Remove the unsafe path and reconcile again.")
        return
    result.pass_check(label, str(path))


def _check_directory(result: DoctorResult, path: Path, label: str) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        result.fail(label, f"Missing required directory: {path}", "Run Station reconcile after reviewing the desired state.")
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        result.fail(label, f"Required path is not a real directory: {path}", "Remove the unsafe path and reconcile again.")
        return
    result.pass_check(label, str(path))


def repo_doctor(repo_root: Path) -> DoctorResult:
    repo_root = Path(repo_root)
    result = DoctorResult("repository")
    required = [
        "README.md",
        "ARCHITECTURE.md",
        "INSTALL.md",
        "SETUP.md",
        "SECURITY.md",
        "AGENTS.md",
        "GEMINI.md",
        "atlas.md",
        "CHANGELOG_V11.md",
        "VALIDATION.md",
        "FILE_INDEX.md",
        "MANIFEST.json",
        "RELEASE_PROVENANCE.json",
        "SBOM.cdx.json",
        "VERSION",
        "station",
        "install",
        "station.sh",
        "bootstrap.sh",
        "scripts/station_toolchain_install.sh",
        "scripts/station_deps_install.sh",
        "scripts/station_guided_setup_enable.sh",
        "scripts/station_hermes_update.sh",
        "scripts/station_parakeet_transcribe.sh",
        "scripts/generate_release_metadata.py",
        "config/versions.lock",
        "config/deps/stack.yaml",
        "config/hermes/voice.default.yaml",
        "config/agent-runtime-policy.json",
        "config/composio/discord-tool-policy.json",
        "rules/STATION_AGENT_RULES.md",
        "runtime/systemd/station-guided-setup.service",
        "runtime/systemd/station-parakeet.service",
        "docs/dependencies/VOICE_AND_GUIDED_SETUP.md",
        "resources/CATALOG.json",
        "resources/discord-js-sdk/package-lock.json",
        "os/devops/semantics/CONTRACT.json",
        "os/devops/programs/runner.py",
        "src/agentik_station/hermes_platforms.py",
        "installer/install_station.py",
        "src/agentik_station/installer.py",
        "src/agentik_station/filesystem.py",
        "src/agentik_station/remote.py",
        "pyproject.toml",
        "contracts/release-manifest.schema.json",
        "docs/hardening/README.md",
        "modules/catalog.json",
        "os/CATALOG.json",
    ]
    for relative in required:
        _check_regular(result, repo_root / relative, f"repo:{relative}")

    version_path = repo_root / "VERSION"
    if version_path.is_file() and not version_path.is_symlink():
        version = version_path.read_text(encoding="utf-8").strip()
        if version != PRODUCT_VERSION:
            result.fail(
                "repo:version",
                f"VERSION is {version!r}, expected {PRODUCT_VERSION!r}",
                "Align VERSION with the Station package version before release.",
            )
        else:
            result.pass_check("repo:version", version)

    manifest_path = repo_root / "MANIFEST.json"
    try:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("MANIFEST.json is missing or unsafe")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("MANIFEST.json root must be an object")
        expected_header = {
            "schema_version": 2,
            "name": "agentik-station",
            "release": PRODUCT_VERSION,
            "blueprint_version": 11,
            "posture": "final-repository-candidate",
            "archive_root": "agentik-station",
            "verified_claim": "READY_FOR_SETUP",
            "history_is_non_canonical": True,
        }
        for field, expected in expected_header.items():
            if manifest.get(field) != expected:
                raise ValueError(f"release manifest {field} must be {expected!r}")
        files = manifest.get("files")
        if not isinstance(files, list) or files != sorted(set(files)):
            raise ValueError("release manifest files must be a sorted unique array")
        actual_files = sorted(
            str(path.relative_to(repo_root))
            for path in repo_root.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and not any(part.endswith(".egg-info") for part in path.parts)
        )
        if files != actual_files:
            missing = sorted(set(actual_files) - set(files))[:5]
            extra = sorted(set(files) - set(actual_files))[:5]
            raise ValueError(f"release manifest inventory drift; missing={missing}, extra={extra}")
        if manifest.get("file_count") != len(actual_files):
            raise ValueError("release manifest file_count differs from the packaged inventory")
        result.pass_check("repo:release-manifest", f"{len(actual_files)} files")
    except Exception as exc:
        result.fail(
            "repo:release-manifest",
            str(exc),
            "Regenerate MANIFEST.json and FILE_INDEX.md from the exact release tree before packaging.",
        )

    provenance_path = repo_root / "RELEASE_PROVENANCE.json"
    try:
        if provenance_path.is_symlink() or not provenance_path.is_file():
            raise ValueError("RELEASE_PROVENANCE.json is missing or unsafe")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance.get("schema_version") != "agk-release-provenance/v1":
            raise ValueError("release provenance schema is invalid")
        if provenance.get("release") != PRODUCT_VERSION or provenance.get("algorithm") != "sha256":
            raise ValueError("release provenance identity is invalid")
        generated = {"FILE_INDEX.md", "MANIFEST.json", "RELEASE_PROVENANCE.json"}
        if set(provenance.get("excluded_generated_files", [])) != generated:
            raise ValueError("release provenance exclusions are invalid")
        subjects = provenance.get("subjects")
        if not isinstance(subjects, list):
            raise ValueError("release provenance subjects must be an array")
        expected_paths = sorted(
            str(path.relative_to(repo_root))
            for path in repo_root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and ".git" not in path.parts
            and not any(part.endswith(".egg-info") for part in path.parts)
            and str(path.relative_to(repo_root)) not in generated
        )
        observed_paths = [str(item.get("path")) for item in subjects if isinstance(item, dict)]
        if observed_paths != expected_paths or provenance.get("subject_count") != len(expected_paths):
            raise ValueError("release provenance subject inventory drifted")
        for item in subjects:
            target = repo_root / str(item["path"])
            info = os.lstat(target)
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise ValueError(f"unsafe provenance subject: {item['path']}")
            if info.st_size != item.get("size"):
                raise ValueError(f"provenance size mismatch: {item['path']}")
            if hashlib.sha256(target.read_bytes()).hexdigest() != item.get("sha256"):
                raise ValueError(f"provenance hash mismatch: {item['path']}")
            if bool(info.st_mode & 0o111) != item.get("executable"):
                raise ValueError(f"provenance mode mismatch: {item['path']}")
        result.pass_check("repo:release-provenance", f"{len(subjects)} sha256 subjects")
    except Exception as exc:
        result.fail(
            "repo:release-provenance",
            str(exc),
            "Run scripts/generate_release_metadata.py after the final source change, then review the provenance.",
        )

    for cache_name in ["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"]:
        found = [p for p in repo_root.rglob(cache_name) if p.is_dir()]
        if found:
            result.fail(
                f"repo:hygiene:{cache_name}",
                f"Generated cache directories are committed: {found[:3]}",
                "Delete generated caches and rebuild the release package.",
            )
        else:
            result.pass_check(f"repo:hygiene:{cache_name}")
    pyc = list(repo_root.rglob("*.pyc"))
    if pyc:
        result.fail("repo:hygiene:pyc", f"Compiled Python artifacts are present: {pyc[:3]}", "Delete *.pyc files.")
    else:
        result.pass_check("repo:hygiene:pyc")

    casefolded: dict[str, Path] = {}
    collisions: list[tuple[Path, Path]] = []
    for path in repo_root.rglob("*"):
        if ".git" in path.parts:
            continue
        relative = path.relative_to(repo_root)
        folded = str(relative).casefold()
        if folded in casefolded:
            collisions.append((casefolded[folded], relative))
        else:
            casefolded[folded] = relative
    if collisions:
        result.fail(
            "repo:hygiene:case-collisions",
            f"Repository paths collide on case-insensitive filesystems: {collisions[:3]}",
            "Rename or remove case-only duplicate paths and regenerate the release manifest.",
        )
    else:
        result.pass_check("repo:hygiene:case-collisions")

    versions_path = repo_root / "config" / "versions.lock"
    try:
        pins = {}
        for line in versions_path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            pins[key] = value
        required_pins = {
            "HERMES_RELEASE",
            "HERMES_COMMIT",
            "HERMES_INSTALL_SHA256",
            "PYTHON_VERSION",
            "AI_PYTHON_VERSION",
            "HERMES_PYTHON_VERSION",
            "UV_VERSION",
            "NODE_VERSION",
            "GITHUB_CLI_VERSION",
            "VERCEL_CLI_VERSION",
            "CODEX_CLI_VERSION",
            "COMPOSIO_CLI_VERSION",
            "COMPOSIO_INSTALL_SHA256",
            "SHADCN_CLI_VERSION",
            "SHADCN_CLI_INTEGRITY",
            "NEXTJS_VERSION",
            "REACT_VERSION",
            "CONVEX_VERSION",
            "CLERK_NEXTJS_VERSION",
            "STRIPE_NODE_VERSION",
            "STRIPE_JS_VERSION",
            "LUCIDE_REACT_VERSION",
            "TAILWINDCSS_VERSION",
            "TYPESCRIPT_VERSION",
            "ESLINT_VERSION",
            "ESLINT_CONFIG_NEXT_VERSION",
            "TYPES_NODE_VERSION",
            "TYPES_REACT_VERSION",
            "TYPES_REACT_DOM_VERSION",
        }
        missing_pins = sorted(required_pins - pins.keys())
        if missing_pins or any(not pins[key] for key in required_pins & pins.keys()):
            raise ValueError(f"missing/empty toolchain pins: {missing_pins}")
        if pins["PYTHON_VERSION"].startswith(pins["HERMES_PYTHON_VERSION"] + "."):
            raise ValueError("latest user Python and Hermes compatibility Python must be separate pins")
        if pins["AI_PYTHON_VERSION"].startswith(pins["HERMES_PYTHON_VERSION"] + "."):
            raise ValueError("AI compatibility Python and Hermes compatibility Python must be separate pins")
        result.pass_check("repo:toolchain-pins", f"{len(pins)} pins")
    except Exception as exc:
        result.fail(
            "repo:toolchain-pins",
            str(exc),
            "Repair config/versions.lock with explicit reviewed toolchain and Hermes pins.",
        )

    symlinks = ensure_no_symlinks(repo_root)
    if symlinks:
        result.fail(
            "repo:symlinks",
            f"Repository release contains symlinks: {symlinks[:5]}",
            "Replace repository symlinks with regular files or generated release artifacts.",
        )
    else:
        result.pass_check("repo:symlinks")

    installed_claims = list(repo_root.rglob("installed.yaml")) + list(repo_root.rglob("installed.yml"))
    if installed_claims:
        result.fail(
            "repo:evidence-before-claims",
            f"Legacy installed.yaml claims remain: {installed_claims[:5]}",
            "Replace them with desired declarations and observed runtime receipts.",
        )
    else:
        result.pass_check("repo:evidence-before-claims")

    duplicate_systemd = repo_root / "runtime" / "hermes-station" / "systemd"
    if duplicate_systemd.exists():
        result.fail(
            "repo:systemd-source",
            "A second systemd source tree remains under runtime/hermes-station/systemd.",
            "Keep runtime/systemd as the only canonical unit source.",
        )
    else:
        result.pass_check("repo:systemd-source")

    try:
        load_station_config(repo_root)
        result.pass_check("repo:station-config")
    except Exception as exc:
        result.fail(
            "repo:station-config",
            str(exc),
            "Repair config/station.default.json and every referenced OS package before release.",
        )

    try:
        module_catalog = load_catalog(repo_root / "modules" / "catalog.json")
        if module_catalog.get("release") != PRODUCT_VERSION:
            raise ValueError("module catalog release does not match VERSION")
        result.pass_check("repo:module-catalog")
    except Exception as exc:
        result.fail("repo:module-catalog", str(exc), "Repair modules/catalog.json and its maturity claims.")

    try:
        os_catalog = load_os_catalog(repo_root / "os" / "CATALOG.json")
        if os_catalog.get("release") != PRODUCT_VERSION:
            raise ValueError("OS catalog release does not match VERSION")
        packages = os_catalog["packages"]
        for package in packages:
            if package.get("runtime_state") != "NOT_INSTALLED":
                raise ValueError(f"Repository package {package.get('id')} makes an unsupported runtime claim")
            source = repo_root / str(package["path"])
            source_result = doctor_os_source(source, expected_id=str(package["id"]))
            if not source_result.ok:
                raise ValueError(f"OS source Doctor failed for {package['id']}: {source_result.issues[:2]}")
        result.pass_check("repo:os-catalog", f"{len(packages)} canonical OS sources pass AGK OS v2 Doctor")
    except Exception as exc:
        result.fail("repo:os-catalog", str(exc), "Correct package maturity and runtime claims.")

    plugin_manifest = repo_root / "runtime" / "hermes-station" / "hermes" / "plugins" / "station-discord-experience" / "plugin.yaml"
    if plugin_manifest.is_file():
        text = plugin_manifest.read_text(encoding="utf-8")
        required_keys = ["provides_tools:", "provides_hooks:", "pre_tool_call"]
        missing = [key for key in required_keys if key not in text]
        if missing:
            result.fail(
                "repo:discord-plugin-manifest",
                f"Plugin manifest lacks declarations: {missing}",
                "Declare registered tools/hooks and validate against the pinned Hermes version.",
            )
        else:
            result.pass_check("repo:discord-plugin-manifest")

    active_python = [
        repo_root / "installer" / "install_station.py",
        repo_root / "src" / "agentik_station" / "installer.py",
        repo_root / "src" / "agentik_station" / "cli.py",
        repo_root / "src" / "agentik_station" / "remote.py",
        repo_root / "src" / "agentik_station" / "identity.py",
        repo_root / "src" / "agentik_station" / "hermes_updates.py",
    ]
    # Keep detector literals out of the scanned implementation files to avoid
    # self-matches while still covering every command-execution surface.
    unsafe_patterns = {
        "shell-true": re.compile(r"shell\s*=\s*True"),
        "piped-network-installer": re.compile(r"(?:curl|wget)[^\n]*\|\s*(?:sh|bash)"),
    }
    for label, compiled in unsafe_patterns.items():
        hits = []
        for path in active_python:
            if path.is_file() and compiled.search(path.read_text(encoding="utf-8", errors="ignore")):
                hits.append(path)
        if hits:
            result.fail(
                f"repo:unsafe-pattern:{label}",
                f"Unsafe execution pattern found in active code: {hits}",
                "Use argv execution and explicit staged/provider-approved installers.",
            )
        else:
            result.pass_check(f"repo:unsafe-pattern:{label}")

    for executable in [repo_root / "station", repo_root / "install", repo_root / "station.sh", repo_root / "bootstrap.sh", repo_root / "installer" / "install_station.py"]:
        if executable.is_file() and (os.stat(executable).st_mode & 0o111):
            result.pass_check(f"repo:executable:{executable.relative_to(repo_root)}")
        else:
            result.fail(
                f"repo:executable:{executable.relative_to(repo_root)}",
                f"Required entrypoint is not executable: {executable}",
                "Restore the executable bit before packaging the release.",
            )

    canonical = [repo_root / "README.md", repo_root / "ARCHITECTURE.md", repo_root / "AGENTS.md"]
    for path in canonical:
        if path.is_file() and re.search(r"\bCells?\b", path.read_text(encoding="utf-8"), re.I):
            result.fail(
                "repo:terminology",
                f"Deprecated isolation terminology appears in {path}",
                "Use Zone consistently in canonical architecture documents.",
            )
    if not any(issue["name"] == "repo:terminology" for issue in result.issues):
        result.pass_check("repo:terminology")

    forbidden = "nutri" + "tion"
    hits: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if "docs/history" in str(path) :
            continue
        try:
            if forbidden in path.read_text(encoding="utf-8", errors="ignore").lower():
                hits.append(str(path.relative_to(repo_root)))
        except OSError:
            continue
    if hits:
        result.fail("repo:forbidden-legacy", f"Forbidden legacy references found: {hits[:5]}", "Remove them from active content.")
    else:
        result.pass_check("repo:forbidden-legacy")

    return result


def _load_json(result: DoctorResult, path: Path, label: str) -> dict[str, Any] | None:
    try:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise ValueError("not a regular non-symlink file")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("root is not an object")
        result.pass_check(label)
        return payload
    except Exception as exc:
        result.fail(label, f"Cannot load {path}: {exc}", "Reconcile Station from the active desired state.")
        return None


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _check_mode(result: DoctorResult, path: Path, allowed: set[int], label: str) -> None:
    try:
        value = _mode(path)
    except OSError as exc:
        result.fail(label, f"Cannot inspect mode for {path}: {exc}", "Repair the path and reconcile.")
        return
    if value not in allowed:
        result.fail(label, f"Unsafe mode {oct(value)} for {path}; expected one of {[oct(v) for v in sorted(allowed)]}", "Restore canonical permissions.")
    else:
        result.pass_check(label, oct(value))



_STATION_DESIRED_FIELDS = {
    "schema_version",
    "station_id",
    "host_id",
    "role",
    "release_version",
    "operation_id",
    "paths",
    "policy",
    "external_modules",
}


def _validate_station_desired(
    payload: dict[str, Any],
    *,
    paths: LayoutPaths,
    repo_root: Path | None,
) -> None:
    _exact_fields(payload, _STATION_DESIRED_FIELDS, "Station desired state")
    if payload.get("schema_version") != 1:
        raise ValueError("Station desired state schema_version must be 1")
    validate_identifier(str(payload.get("station_id", "")), "station_id")
    validate_identifier(str(payload.get("host_id", "")), "host_id")
    role = payload.get("role")
    if role not in ROLES:
        raise ValueError(f"Station desired state has unsupported Host role {role!r}")
    version = validate_version(str(payload.get("release_version", "")))
    if version != PRODUCT_VERSION:
        raise ValueError(f"Station desired release {version!r} differs from active package {PRODUCT_VERSION!r}")
    validate_operation_id(str(payload.get("operation_id", "")))
    expected_paths = {
        "config": str(paths.config),
        "software": str(paths.software),
        "runtime": str(paths.runtime),
        "state": str(paths.varlib),
    }
    if payload.get("paths") != expected_paths:
        raise ValueError(f"Station desired paths differ from the canonical Host layout: {payload.get('paths')!r}")
    external = payload.get("external_modules")
    if not isinstance(external, dict) or set(external) != {"hermes", "discord", "composio", "tailscale"}:
        raise ValueError("Station desired external_modules keys are invalid")
    allowed_external_states = {"NOT_CONFIGURED", "DESIRED", "CONFIGURED", "VERIFIED", "OPERATIONAL", "DEGRADED"}
    for module, state in external.items():
        if state not in allowed_external_states:
            raise ValueError(f"External module {module} has invalid desired state {state!r}")
    if repo_root is not None:
        config = load_station_config(repo_root)
        if payload.get("station_id") != config.station_id:
            raise ValueError("Installed station_id differs from the active release configuration")
        if payload.get("policy") != config.policy:
            raise ValueError("Installed Station policy differs from the active release policy")


_LOCAL_ZONE_FIELDS = {
    "schema_version",
    "id",
    "name",
    "category",
    "organization",
    "environment",
    "host_id",
    "unix_user",
    "human_root",
    "state_root",
    "hermes_home",
    "log_root",
    "runtime_root",
    "backup_staging_root",
    "placement",
    "isolation",
}
_REMOTE_ZONE_FIELDS = {
    "schema_version",
    "id",
    "category",
    "organization",
    "environment",
    "host_id",
    "placement",
    "runtime_state",
    "next_repair_action",
}
_PROJECT_FIELDS = {
    "schema_version",
    "id",
    "zone_id",
    "organization",
    "environment",
    "human_root",
    "runtime_state_root",
    "repos",
    "credential_references",
}
_OS_DESIRED_FIELDS = {"schema_version", "zone_id", "packages"}
_OS_DESIRED_PACKAGE_FIELDS = {"id", "desired", "package_maturity", "runtime_state", "claim"}


def _exact_fields(payload: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing or unknown:
        raise ValueError(f"{label} fields mismatch; missing={missing}, unknown={unknown}")


def _expected_zone_human_path(paths: LayoutPaths, zone: ZoneSpec) -> Path:
    base = paths.runtime / "2_ZONES" / CATEGORIES[zone.category]
    if zone.category in {"ORGANIZATIONS", "PROJECTS"}:
        return base / zone.name / environment_slug(zone.environment)
    return base / zone.name


def _validate_local_zone_record(
    payload: dict[str, Any],
    *,
    record_path: Path,
    paths: LayoutPaths,
    expected_host_id: str | None,
) -> tuple[ZoneSpec, Path, Path, str]:
    _exact_fields(payload, _LOCAL_ZONE_FIELDS, "local Zone record")
    if payload.get("schema_version") != 2:
        raise ValueError("local Zone schema_version must be 2")
    if payload.get("placement") != "local":
        raise ValueError("local Zone placement must be 'local'")
    isolation = payload.get("isolation")
    expected_isolation = {
        "filesystem": "unix-identity",
        "hermes_home": "dedicated",
        "credentials": "zone-scoped",
        "cross_zone_mounts": "deny",
    }
    if isolation != expected_isolation:
        raise ValueError("local Zone isolation contract differs from the canonical v11 contract")

    zone = ZoneSpec(
        category=str(payload["category"]),
        name=str(payload["name"]),
        environment=str(payload["environment"]),
        host_id=str(payload["host_id"]),
        organization=validate_optional_identifier(payload.get("organization"), "Zone organization"),
    )
    if payload["id"] != zone.zone_id:
        raise ValueError(f"Zone id {payload['id']!r} does not match canonical id {zone.zone_id!r}")
    if record_path.stem != zone.zone_id:
        raise ValueError(f"Zone record filename {record_path.name!r} does not match Zone id {zone.zone_id!r}")
    if expected_host_id and zone.host_id != expected_host_id:
        raise ValueError(f"Zone host_id {zone.host_id!r} differs from Station host_id {expected_host_id!r}")

    expected_user = zone_unix_user(zone.category, zone.name, zone.environment)
    if payload["unix_user"] != expected_user:
        raise ValueError(f"Zone unix_user {payload['unix_user']!r} does not match {expected_user!r}")

    human = _expected_zone_human_path(paths, zone)
    state_root = paths.zones_state / zone.zone_id
    expected_paths = {
        "human_root": human,
        "state_root": state_root,
        "hermes_home": state_root / "hermes",
        "log_root": paths.log / "zones" / zone.zone_id,
        "runtime_root": paths.run / "zones" / zone.zone_id,
        "backup_staging_root": paths.backups / "zones" / zone.zone_id,
    }
    for field, expected in expected_paths.items():
        if payload[field] != str(expected):
            raise ValueError(f"Zone {field} must be exactly {expected}; got {payload[field]!r}")
    return zone, human, state_root, expected_user


def _validate_remote_zone_record(payload: dict[str, Any], *, record_path: Path) -> None:
    _exact_fields(payload, _REMOTE_ZONE_FIELDS, "remote Zone desired record")
    if payload.get("schema_version") != 1:
        raise ValueError("remote Zone desired schema_version must be 1")
    if payload.get("placement") != "REMOTE_DESIRED_NOT_APPLIED":
        raise ValueError("remote Zone desired placement is invalid")
    if payload.get("runtime_state") != "NOT_INSTALLED":
        raise ValueError("remote Zone desired state may not claim runtime installation")
    next_action = payload.get("next_repair_action")
    if not isinstance(next_action, str) or not next_action.strip():
        raise ValueError("remote Zone desired record requires next_repair_action")
    category = str(payload.get("category", "")).upper()
    if category not in {"ORGANIZATIONS", "PROJECTS"}:
        raise ValueError("remote desired Zones are limited to ORGANIZATIONS or PROJECTS")
    name_and_env = str(payload.get("id", ""))
    validate_identifier(name_and_env, "remote Zone id")
    host_id = validate_identifier(str(payload.get("host_id", "")), "remote Zone host_id")
    organization = validate_optional_identifier(payload.get("organization"), "remote Zone organization")
    environment = normalize_deploy_environment(str(payload.get("environment", "")))
    suffix = f"-{environment_slug(environment)}"
    if not name_and_env.endswith(suffix):
        raise ValueError("remote Zone id does not encode its environment")
    name = name_and_env[: -len(suffix)]
    zone = ZoneSpec(category, name, environment, host_id, organization)
    if zone.zone_id != name_and_env:
        raise ValueError("remote Zone id does not match the canonical ZoneSpec id")
    expected_filename = f"remote-{host_id}-{zone.zone_id}.json"
    if record_path.name != expected_filename:
        raise ValueError(f"remote Zone desired filename must be {expected_filename!r}")


def _validate_os_desired(
    payload: dict[str, Any],
    *,
    zone_id: str,
    catalog_by_id: dict[str, dict[str, Any]],
) -> None:
    _exact_fields(payload, _OS_DESIRED_FIELDS, "OS desired record")
    if payload.get("schema_version") != 1 or payload.get("zone_id") != zone_id:
        raise ValueError("OS desired record schema/zone_id mismatch")
    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise ValueError("OS desired packages must be an array")
    seen: set[str] = set()
    for item in packages:
        if not isinstance(item, dict):
            raise ValueError("Every OS desired package must be an object")
        _exact_fields(item, _OS_DESIRED_PACKAGE_FIELDS, "OS desired package")
        package_id = validate_identifier(str(item.get("id", "")), "OS package id")
        if package_id in seen:
            raise ValueError(f"Duplicate desired OS package: {package_id}")
        seen.add(package_id)
        catalog_item = catalog_by_id.get(package_id)
        if catalog_item is None:
            raise ValueError(f"Desired OS package is absent from the release catalog: {package_id}")
        if item.get("desired") is not True:
            raise ValueError(f"Desired OS package {package_id} must set desired=true")
        if item.get("package_maturity") != catalog_item.get("maturity"):
            raise ValueError(f"Desired OS package {package_id} maturity drifts from the release catalog")
        if item.get("runtime_state") != "NOT_INSTALLED":
            raise ValueError(f"Desired OS package {package_id} makes an unsupported runtime claim")
        if item.get("claim") != "DECLARED_ONLY":
            raise ValueError(f"Desired OS package {package_id} claim must be DECLARED_ONLY")


def _validate_project_record(
    payload: dict[str, Any],
    *,
    zone: ZoneSpec,
    project_path: Path,
    paths: LayoutPaths,
) -> tuple[str, Path]:
    _exact_fields(payload, _PROJECT_FIELDS, "Project record")
    if payload.get("schema_version") != 2:
        raise ValueError("Project schema_version must be 2")
    project_id = validate_identifier(str(payload.get("id", "")), "project id")
    if project_path.name != project_id:
        raise ValueError("Project directory name differs from Project id")
    if payload.get("zone_id") != zone.zone_id:
        raise ValueError("Project zone_id differs from its containing Zone")
    if payload.get("organization") != zone.organization:
        raise ValueError("Project organization differs from its containing Zone")
    if payload.get("environment") != zone.environment:
        raise ValueError("Project environment differs from its containing Zone")
    expected_human = project_path
    expected_state = paths.zones_state / zone.zone_id / "projects" / project_id
    if payload.get("human_root") != str(expected_human):
        raise ValueError("Project human_root differs from its canonical Zone path")
    if payload.get("runtime_state_root") != str(expected_state):
        raise ValueError("Project runtime_state_root differs from its canonical Zone state path")
    if not isinstance(payload.get("repos"), list) or not isinstance(payload.get("credential_references"), list):
        raise ValueError("Project repos and credential_references must be arrays")
    return project_id, expected_state

def station_doctor(
    paths: LayoutPaths,
    *,
    repo_root: Path | None = None,
    full: bool = False,
    expect_operation: str | None = None,
) -> DoctorResult:
    result = DoctorResult("station-full" if full else "station")
    directories = {
        "fhs:config": paths.config,
        "fhs:software": paths.software,
        "fhs:releases": paths.releases,
        "fhs:runtime": paths.runtime,
        "fhs:control-projection": paths.runtime / "1_CONTROL",
        "fhs:zones": paths.runtime / "2_ZONES",
        "fhs:shared": paths.runtime / "3_SHARED",
        "fhs:archive": paths.runtime / "4_ARCHIVE",
        "fhs:state": paths.varlib,
        "fhs:receipts": paths.receipts,
        "fhs:zone-state": paths.zones_state,
        "fhs:logs": paths.log,
        "fhs:run": paths.run,
    }
    for label, path in directories.items():
        _check_directory(result, path, label)
    for category in CATEGORIES.values():
        _check_directory(result, paths.runtime / "2_ZONES" / category, f"category:{category}")

    desired = _load_json(result, paths.config / "station.json", "desired:station")
    observed = _load_json(result, paths.observed / "host.json", "observed:host")
    if desired:
        try:
            _validate_station_desired(desired, paths=paths, repo_root=repo_root)
            result.pass_check("desired:station-contract")
        except Exception as exc:
            result.fail(
                "desired:station-contract",
                str(exc),
                "Restore canonical Station desired state from the active immutable release and reconcile.",
            )

    try:
        st = os.lstat(paths.current)
        if not stat.S_ISLNK(st.st_mode):
            raise ValueError("current is not a symlink")
        target = os.readlink(paths.current)
        expected_target = f"releases/{desired['release_version']}" if desired else f"releases/{PRODUCT_VERSION}"
        if target != expected_target:
            raise ValueError(f"active release target must be {expected_target!r}; got {target!r}")
        release = paths.software / target
        if release.is_symlink() or not release.is_dir():
            raise ValueError(f"active release does not exist: {release}")
        release_version = release / "VERSION"
        if release_version.is_symlink() or not release_version.is_file():
            raise ValueError("active release VERSION is missing or unsafe")
        if release_version.read_text(encoding="utf-8").strip() != Path(target).name:
            raise ValueError("active release VERSION differs from its immutable directory name")
        result.pass_check("release:current", target)
        if full:
            links = ensure_no_symlinks(release)
            if links:
                raise ValueError(f"active immutable release contains symlinks: {links[:5]}")
            writable = []
            for candidate in release.rglob("*"):
                try:
                    mode = os.lstat(candidate).st_mode
                except OSError:
                    continue
                if mode & 0o222:
                    writable.append(str(candidate))
                    if len(writable) >= 5:
                        break
            if writable:
                raise ValueError(f"active immutable release contains writable paths: {writable}")
            result.pass_check("release:immutable-tree")
    except Exception as exc:
        result.fail("release:current", str(exc), "Activate a valid immutable release under /opt/station/releases.")

    try:
        st = os.lstat(paths.bin / "station")
        if not stat.S_ISLNK(st.st_mode):
            raise ValueError("station command is not a symlink")
        target = os.readlink(paths.bin / "station")
        expected_target = str(paths.current / "station")
        if target != expected_target:
            raise ValueError(f"station command must point exactly to {expected_target}; got {target}")
        result.pass_check("release:command", target)
    except Exception as exc:
        result.fail("release:command", str(exc), "Reconcile the Station command symlink.")

    _check_mode(result, paths.config, {0o750}, "mode:/etc/station")
    _check_mode(result, paths.runtime, {0o755}, "mode:/srv/station")
    _check_mode(result, paths.varlib, {0o750}, "mode:/var/lib/station")

    catalog_by_id: dict[str, dict[str, Any]] = {}
    if repo_root is not None:
        try:
            os_catalog = load_os_catalog(Path(repo_root) / "os" / "CATALOG.json")
            catalog_by_id = {str(item["id"]): item for item in os_catalog["packages"]}
            result.pass_check("runtime:os-catalog")
        except Exception as exc:
            result.fail(
                "runtime:os-catalog",
                str(exc),
                "Repair the active release OS catalog before trusting desired package records.",
            )

    zone_records: list[tuple[Path, dict[str, Any]]] = []
    zones_dir = paths.config / "zones.d"
    if zones_dir.is_dir() and not zones_dir.is_symlink():
        for record_path in sorted(zones_dir.glob("*.json")):
            payload = _load_json(result, record_path, f"zone-record:{record_path.stem}")
            if payload:
                zone_records.append((record_path, payload))

    expected_host_id = str(desired.get("host_id")) if desired else None
    for record_path, payload in zone_records:
        if payload.get("placement") == "REMOTE_DESIRED_NOT_APPLIED":
            try:
                _validate_remote_zone_record(payload, record_path=record_path)
                result.pass_check(f"zone-record:{record_path.stem}:contract", "remote desired state only")
            except Exception as exc:
                result.fail(
                    f"zone-record:{record_path.stem}:contract",
                    str(exc),
                    "Repair or remove the malformed remote desired-state record; do not contact its Host.",
                )
            continue

        try:
            zone, human, state_root, user_name = _validate_local_zone_record(
                payload,
                record_path=record_path,
                paths=paths,
                expected_host_id=expected_host_id,
            )
            result.pass_check(f"zone:{zone.zone_id}:contract")
        except Exception as exc:
            label = str(payload.get("id") or record_path.stem)
            result.fail(
                f"zone:{label}:contract",
                str(exc),
                "Restore the local Zone record from canonical desired state before inspecting or starting its runtime.",
            )
            # Never lstat or traverse paths supplied by an invalid record.
            continue

        zone_id = zone.zone_id
        _check_directory(result, human, f"zone:{zone_id}:human")
        _check_directory(result, state_root, f"zone:{zone_id}:state")
        _check_directory(result, human / "credentials", f"zone:{zone_id}:credentials")
        _check_directory(result, state_root / "hermes", f"zone:{zone_id}:hermes-home")
        _check_regular(result, state_root / "home" / ".config" / "containers" / "storage.conf", f"zone:{zone_id}:rootless-storage-config")
        _check_regular(result, state_root / "home" / ".config" / "containers" / "containers.conf", f"zone:{zone_id}:rootless-container-config")
        _check_regular(result, state_root / "rootless" / "POLICY.json", f"zone:{zone_id}:rootless-policy")
        if (human / "credentials").exists():
            _check_mode(result, human / "credentials", {0o700}, f"zone:{zone_id}:credentials-mode")

        zone_manifest = _load_json(result, human / "ZONE.json", f"zone:{zone_id}:manifest")
        if zone_manifest is not None:
            if zone_manifest != payload:
                result.fail(
                    f"zone:{zone_id}:manifest-match",
                    "ZONE.json differs from the root-owned canonical Zone record.",
                    "Reconcile the Zone and investigate unauthorized or accidental drift.",
                )
            else:
                result.pass_check(f"zone:{zone_id}:manifest-match")

        os_desired_path = human / "os" / "DESIRED.json"
        os_desired = _load_json(result, os_desired_path, f"zone:{zone_id}:os-desired")
        if os_desired is not None and catalog_by_id:
            try:
                _validate_os_desired(os_desired, zone_id=zone_id, catalog_by_id=catalog_by_id)
                result.pass_check(f"zone:{zone_id}:os-desired-contract")
            except Exception as exc:
                result.fail(
                    f"zone:{zone_id}:os-desired-contract",
                    str(exc),
                    "Recompile desired OS declarations from the active release catalog.",
                )

        unsafe_links = ensure_no_symlinks(human) + ensure_no_symlinks(state_root)
        if unsafe_links:
            result.fail(
                f"zone:{zone_id}:symlinks",
                f"Unexpected symlinks exist in the Zone roots: {unsafe_links[:5]}",
                "Remove the symlinks or replace them with an explicitly governed mount/binding contract.",
            )
        else:
            result.pass_check(f"zone:{zone_id}:symlinks")

        if not paths.test_mode:
            try:
                entry = pwd.getpwnam(user_name)
                group = grp.getgrnam(user_name)
                if entry.pw_gid != group.gr_gid:
                    result.fail(
                        f"zone:{zone_id}:identity-primary-group",
                        f"User {user_name} primary gid {entry.pw_gid} differs from canonical group gid {group.gr_gid}",
                        "Repair the Unix identity before starting any Zone service.",
                    )
                else:
                    result.pass_check(f"zone:{zone_id}:identity-primary-group")
                for check_path in [human, state_root, human / "credentials", state_root / "hermes"]:
                    st = os.lstat(check_path)
                    if (st.st_uid, st.st_gid) != (entry.pw_uid, group.gr_gid):
                        result.fail(
                            f"zone:{zone_id}:ownership",
                            f"{check_path} is owned by {st.st_uid}:{st.st_gid}, expected {entry.pw_uid}:{group.gr_gid}",
                            "Repair exact Zone ownership; do not recursively follow symlinks.",
                        )
                        break
                else:
                    result.pass_check(f"zone:{zone_id}:ownership", user_name)
            except KeyError:
                result.fail(
                    f"zone:{zone_id}:identity",
                    f"Unix user/group {user_name!r} does not exist",
                    "Reconcile the Zone identity before starting Hermes or Project services.",
                )

        projects = human / "projects"
        if projects.is_dir() and not projects.is_symlink():
            for project in sorted(projects.iterdir()):
                if project.is_symlink() or not project.is_dir():
                    result.fail(
                        f"project:{zone_id}:{project.name}",
                        f"Unexpected Project path type: {project}",
                        "Remove the unsafe path and reconcile the Project.",
                    )
                    continue
                project_manifest = _load_json(
                    result,
                    project / "PROJECT.json",
                    f"project:{zone_id}:{project.name}:manifest",
                )
                if project_manifest is None:
                    continue
                try:
                    project_id, project_state = _validate_project_record(
                        project_manifest,
                        zone=zone,
                        project_path=project,
                        paths=paths,
                    )
                    result.pass_check(f"project:{zone_id}:{project.name}:contract")
                except Exception as exc:
                    result.fail(
                        f"project:{zone_id}:{project.name}:contract",
                        str(exc),
                        "Restore the Project manifest from canonical Zone desired state before starting its runtime.",
                    )
                    continue
                _check_directory(result, project / "credentials", f"project:{zone_id}:{project_id}:credentials")
                _check_directory(result, project / "resources", f"project:{zone_id}:{project_id}:resources")
                _check_regular(
                    result,
                    project / ".station" / "STATION_AGENT_RULES.md",
                    f"project:{zone_id}:{project_id}:agent-rules",
                )
                _check_regular(result, project / "AGENTS.md", f"project:{zone_id}:{project_id}:agents-entrypoint")
                _check_directory(result, project_state, f"project:{zone_id}:{project_id}:state")
                if (project / "credentials").exists():
                    _check_mode(
                        result,
                        project / "credentials",
                        {0o700},
                        f"project:{zone_id}:{project_id}:credentials-mode",
                    )
                project_links = ensure_no_symlinks(project) + ensure_no_symlinks(project_state)
                if project_links:
                    result.fail(
                        f"project:{zone_id}:{project_id}:symlinks",
                        f"Unexpected symlinks exist in Project roots: {project_links[:5]}",
                        "Remove the symlinks or define an explicit governed mount contract.",
                    )
                else:
                    result.pass_check(f"project:{zone_id}:{project_id}:symlinks")
                if not paths.test_mode:
                    try:
                        entry = pwd.getpwnam(user_name)
                        group = grp.getgrnam(user_name)
                        for check_path in [project, project / "credentials", project_state]:
                            st = os.lstat(check_path)
                            if (st.st_uid, st.st_gid) != (entry.pw_uid, group.gr_gid):
                                result.fail(
                                    f"project:{zone_id}:{project_id}:ownership",
                                    f"{check_path} is owned by {st.st_uid}:{st.st_gid}, expected Zone owner {entry.pw_uid}:{group.gr_gid}",
                                    "Repair Project ownership through Station reconciliation.",
                                )
                                break
                        else:
                            result.pass_check(f"project:{zone_id}:{project_id}:ownership")
                    except KeyError:
                        pass

    if expect_operation:
        receipt_path = paths.receipts / f"{expect_operation}.json"
        receipt = _load_json(result, receipt_path, f"receipt:{expect_operation}")
        if receipt and receipt.get("status") == "FAILED":
            result.fail(
                f"receipt:{expect_operation}:status",
                "Current operation receipt is FAILED",
                "Repair the recorded failure before continuing.",
            )
        elif receipt:
            result.pass_check(f"receipt:{expect_operation}:status", str(receipt.get("status")))

    if full:
        for unit in ["station-doctor.service", "station-doctor.timer", "station-hermes-watch.service", "station-hermes-watch.timer"]:
            _check_regular(result, paths.systemd / unit, f"systemd:{unit}")
        if not paths.test_mode and shutil.which("systemctl") and Path("/run/systemd/system").is_dir():
            completed = subprocess.run(["systemctl", "is-enabled", "station-doctor.timer"], capture_output=True, text=True)
            if completed.returncode == 0:
                result.pass_check("systemd:doctor-timer-enabled", completed.stdout.strip())
            else:
                result.warn(
                    "systemd:doctor-timer-enabled",
                    "station-doctor.timer is not enabled.",
                    "Enable it after reviewing the unit and desired state.",
                )

        external = {
            "Hermes": shutil.which("hermes"),
            "Python latest": shutil.which("python-latest"),
            "Python AI": shutil.which("python-ai"),
            "Node.js": shutil.which("node"),
            "GitHub CLI": shutil.which("gh"),
            "Vercel CLI": shutil.which("vercel"),
            "Codex CLI": shutil.which("codex"),
            "Composio": shutil.which("composio"),
            "Tailscale": shutil.which("tailscale"),
            "Podman": shutil.which("podman"),
        }
        for name, binary in external.items():
            if binary:
                result.warn(
                    f"external:{name.lower()}",
                    f"Binary available at {binary}; configuration/readback is not inferred from binary presence.",
                    "Run the module-specific setup and verification gate before raising readiness.",
                )
            else:
                result.warn(
                    f"external:{name.lower()}",
                    "Binary not available; this is expected at READY_FOR_SETUP for the safe kernel.",
                    "Enroll the module through the approved setup workflow when needed.",
                )

    if desired and observed:
        if desired.get("host_id") != observed.get("host_id"):
            result.fail("state:host-drift", "Desired and observed host_id differ", "Reconcile the current Host desired state.")
        else:
            result.pass_check("state:host-drift")
        if observed.get("state") == "DEGRADED":
            result.fail(
                "state:degraded",
                str(observed.get("failure") or "Observed Station state is DEGRADED"),
                str(observed.get("next_repair_action") or "Inspect the latest receipt and repair the failed operation."),
            )
        else:
            result.pass_check("state:not-degraded", str(observed.get("state")))

    return result
