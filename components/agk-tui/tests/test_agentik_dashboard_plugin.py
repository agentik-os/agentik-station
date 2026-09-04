from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import re
import sqlite3
import sys
import types
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "hermes" / "plugins" / "agentik_os" / "dashboard"
MANIFEST = DASHBOARD / "manifest.json"
BUNDLE = DASHBOARD / "dist" / "index.js"
STYLES = DASHBOARD / "dist" / "style.css"
PLUGIN_API = DASHBOARD / "plugin_api.py"
THEME = ROOT / "hermes" / "dashboard-themes" / "agentik-shadcn.yaml"
LIGHT_THEME = ROOT / "hermes" / "dashboard-themes" / "agentik-shadcn-light.yaml"


class RecordingRouter:
    """Minimal APIRouter contract for importing the plugin without FastAPI."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Callable[..., Any]] = {}

    def get(self, path: str, *_args: Any, **_kwargs: Any):
        def register(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.routes[("GET", path)] = handler
            return handler

        return register


def _load_api(monkeypatch, *, hermes_home: Path, registry: Path, runtime_db: Path):
    router = RecordingRouter()
    fastapi = types.ModuleType("fastapi")
    fastapi.APIRouter = lambda *_args, **_kwargs: router  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastapi", fastapi)
    monkeypatch.setenv("HOME", str(hermes_home.parent))
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("AGENTIK_ENVIRONMENT", "mission")
    monkeypatch.setenv("USER", "mission")
    monkeypatch.setenv("AGK_OS_REGISTRY", str(registry))
    monkeypatch.setenv("AGK_RUNTIME_DB", str(runtime_db))

    spec = importlib.util.spec_from_file_location(
        "agentik_dashboard_plugin_tested",
        PLUGIN_API,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module.router is router
    return module, router


def _call(handler: Callable[..., Any]) -> Any:
    result = handler()
    return asyncio.run(result) if inspect.isawaitable(result) else result


def test_manifest_matches_the_official_dashboard_plugin_contract():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["name"] == "agentik-os"
    assert manifest["label"] == "OS & Agents"
    assert manifest["version"] == "0.5.0"
    assert manifest["tab"] == {"path": "/os-agents", "position": "after:skills"}
    assert manifest["entry"] == "dist/index.js"
    assert manifest["css"] == "dist/style.css"
    assert manifest["api"] == "plugin_api.py"

    for field in ("entry", "css", "api"):
        relative = Path(manifest[field])
        assert not relative.is_absolute() and ".." not in relative.parts
        assert (DASHBOARD / relative).is_file()


def test_bundle_registers_with_the_official_sdk_and_catalog_endpoint():
    source = BUNDLE.read_text(encoding="utf-8")

    assert "window.__HERMES_PLUGIN_SDK__" in source
    assert "window.__HERMES_PLUGINS__" in source
    assert "/api/plugins/agentik-os/catalog" in source
    assert "fetchJSON" in source
    for component in (
        "Card",
        "CardHeader",
        "CardTitle",
        "CardContent",
        "Badge",
        "Button",
        "Separator",
        "Tabs",
        "TabsList",
        "TabsTrigger",
    ):
        assert component in source
    assert re.search(
        r"\.register\(\s*['\"]agentik-os['\"]\s*,",
        source,
    )
    assert "window.__HERMES_SESSION_TOKEN__" not in source


def test_css_is_scoped_and_has_no_external_hosts():
    source = STYLES.read_text(encoding="utf-8")
    without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    lowered = without_comments.lower()

    assert "@import" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "//" not in lowered
    assert "gradient" not in lowered
    assert "backdrop-filter" not in lowered
    assert "box-shadow" not in lowered

    selector_groups = re.findall(r"([^{}]+)\{", without_comments)
    checked = 0
    for group in selector_groups:
        group = group.strip()
        if not group or group.startswith("@"):
            continue
        for selector in group.split(","):
            selector = selector.strip()
            if re.fullmatch(r"(?:from|to|\d+(?:\.\d+)?%)", selector):
                continue
            assert selector.startswith(".agk-os-hub"), selector
            checked += 1
    assert checked > 0


def test_dashboard_uses_a_responsive_master_detail_panel_layout():
    bundle = BUNDLE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    for contract in (
        "CatalogNavigation",
        "CatalogTrigger",
        "agk-os-workspace",
        "agk-os-context-panel",
        "agk-os-detail-panel",
        "agk-os-detail-body--dashboard",
        "agk-os-detail-body--entity",
    ):
        assert contract in bundle

    assert 'className: "agk-os-tabs"' not in bundle
    assert "grid-template-columns: minmax(15rem, 17rem) minmax(0, 1fr)" in styles
    assert "--agk-panel-radius: 0.75rem" in styles
    assert "--agk-card-radius: 0.625rem" in styles
    assert "--agk-control-radius: 0.5rem" in styles
    assert "gap: var(--agk-panel-gap)" in styles
    assert styles.count("border-radius: var(--agk-panel-radius)") >= 2
    assert "border-radius: var(--agk-card-radius)" in styles
    assert ".agk-os-hub .agk-os-detail-panel {\n    overflow: hidden;" in styles
    assert "scroll-snap-type: x proximity" in styles
    assert "@media (max-width: 640px)" in styles


def test_agentik_shadcn_theme_is_official_local_and_reproducible():
    theme = yaml.safe_load(THEME.read_text(encoding="utf-8"))
    light_theme = yaml.safe_load(LIGHT_THEME.read_text(encoding="utf-8"))

    assert theme["name"] == "agentik-shadcn"
    assert light_theme["name"] == "agentik-shadcn-light"
    for candidate in (theme, light_theme):
        assert candidate["layout"] == {"radius": "0.625rem", "density": "compact"}
        assert candidate["layoutVariant"] == "standard"
        assert candidate["palette"]["noiseOpacity"] == 0
        assert "fontUrl" not in candidate["typography"]
    assert theme["colorOverrides"]["card"] == "#171717"
    assert theme["colorOverrides"]["border"] == "#2f2f2f"
    assert light_theme["colorOverrides"]["card"] == "#ffffff"
    assert light_theme["colorOverrides"]["border"] == "#dfdfdc"
    assert theme["customCSS"].replace("color-scheme: dark", "color-scheme: light") == light_theme["customCSS"]
    assert "--agk-ui-panel-radius: 0.75rem" in theme["customCSS"]
    assert '[class*="font-mondwest"]' in theme["customCSS"]
    assert "#app-sidebar nav a" in theme["customCSS"]

    for theme_path in (THEME, LIGHT_THEME):
        serialized = theme_path.read_text(encoding="utf-8").lower()
        assert "http://" not in serialized
        assert "https://" not in serialized
        assert "gradient" not in serialized
        assert "backdrop-filter" not in serialized

    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    sync = (ROOT / "scripts" / "sync-hermes.sh").read_text(encoding="utf-8")
    for source in (installer, sync):
        assert "hermes/dashboard-themes/agentik-shadcn.yaml" in source
        assert "hermes/dashboard-themes/agentik-shadcn-light.yaml" in source


def test_api_source_keeps_the_canonical_os_dependencies_field():
    source = PLUGIN_API.read_text(encoding="utf-8")

    assert re.search(r"['\"]dependencies['\"]", source)


def test_catalog_api_is_isolated_redacted_and_empty_runtime_safe(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes-home"
    agents_root = hermes_home / "agents"
    agent_root = agents_root / "field-researcher"
    agent_root.mkdir(parents=True)
    prompt_canary = "PROMPT-CONTENTS-MUST-NEVER-LEAVE-THE-SERVER"
    config_canary = "CONFIG-SECRET-MUST-NEVER-LEAVE-THE-SERVER"
    runtime_canary = "RUNTIME-SECRET-MUST-NEVER-LEAVE-THE-SERVER"
    (hermes_home / "config.yaml").write_text(
        "runtime_identity:\n"
        "  machine_id: test-core\n"
        "  environment_id: mission\n"
        f"api_key: {config_canary}\n",
        encoding="utf-8",
    )
    (agent_root / "agent.yaml").write_text(
        "id: field-researcher\n"
        "name: Field Researcher\n"
        "version: 1.2.3\n"
        "description: Researches bounded questions.\n"
        "scope:\n"
        "  - mission\n"
        "runtime: hermes\n"
        "prompt: prompt.md\n"
        "aliases:\n"
        "  - build-os\n"
        "distribution: local\n",
        encoding="utf-8",
    )
    (agent_root / "prompt.md").write_text(prompt_canary, encoding="utf-8")

    registry = tmp_path / "registry"
    (registry / "state").mkdir(parents=True)
    (registry / "state" / "index.json").write_text(
        json.dumps({"schema_version": 1, "packages": []}),
        encoding="utf-8",
    )

    runtime_db = tmp_path / "runtime.db"
    with sqlite3.connect(runtime_db) as database:
        database.execute(
            """
            CREATE TABLE runtime_sessions (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              environment TEXT NOT NULL,
              hermes_session TEXT,
              rmux_session TEXT,
              cwd TEXT,
              status TEXT NOT NULL,
              archived_at REAL,
              native_session TEXT,
              command_json TEXT
            )
            """
        )
        database.execute(
            """
            INSERT INTO runtime_sessions (
              id, name, type, environment, hermes_session, rmux_session,
              cwd, status, archived_at, native_session, command_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "RT-TEST-1",
                "build-os",
                "hermes",
                "mission",
                runtime_canary,
                "mission-build-os",
                str(tmp_path / "secret-workspace"),
                "running",
                None,
                "native-secret-session",
                json.dumps(["hermes", "--token", runtime_canary]),
            ),
        )

    _module, router = _load_api(
        monkeypatch,
        hermes_home=hermes_home,
        registry=registry,
        runtime_db=runtime_db,
    )
    assert set(router.routes) == {("GET", "/catalog")}
    payload = _call(router.routes[("GET", "/catalog")])

    assert set(payload) == {"environment", "registry", "agents", "sync"}
    assert payload["environment"] == "mission"
    assert payload["registry"] == {
        "available": True,
        "healthy": True,
        "package_count": 0,
        "invalid_count": 0,
        "packages": [],
    }
    assert payload["sync"] == {"agent_count": 1, "active_session_count": 1}
    assert len(payload["agents"]) == 1

    agent = payload["agents"][0]
    assert set(agent) == {
        "id",
        "name",
        "version",
        "description",
        "scope",
        "runtime",
        "distribution",
        "prompt_present",
        "allowed_here",
        "definition_hash",
        "sessions",
    }
    assert agent["id"] == "field-researcher"
    assert agent["scope"] == ["mission"]
    assert agent["runtime"] == "hermes"
    assert agent["distribution"] == "local"
    assert agent["prompt_present"] is True
    assert agent["allowed_here"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", agent["definition_hash"])
    assert agent["sessions"] == [
        {
            "id": "RT-TEST-1",
            "name": "build-os",
            "runtime": "hermes",
            "status": "running",
            "active": True,
            "last_activity": None,
            "exit_code": None,
        }
    ]

    serialized = json.dumps(payload, sort_keys=True)
    assert prompt_canary not in serialized
    assert config_canary not in serialized
    assert runtime_canary not in serialized
    assert str(tmp_path) not in serialized
    forbidden_keys = {
        "prompt",
        "prompt_path",
        "path",
        "cwd",
        "command_json",
        "hermes_session",
        "api_key",
        "token",
        "secret",
    }

    def assert_redacted(value: Any) -> None:
        if isinstance(value, dict):
            assert not (set(value) & forbidden_keys)
            for nested in value.values():
                assert_redacted(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_redacted(nested)

    assert_redacted(payload)
