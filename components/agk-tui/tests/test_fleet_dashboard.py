import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "apps" / "hermes-fleet"
FRONTEND_SRC = FRONTEND / "src"
FRONTEND_PUBLIC = FRONTEND / "public"
SERVER_SRC = FRONTEND / "server"
INSTALLER = ROOT / "scripts" / "install-hermes-fleet-dashboard.sh"
HERMES_SERVICE_TEMPLATE = ROOT / "systemd" / "hermes-dashboard.service.in"
FLEET_SERVICE_TEMPLATE = ROOT / "systemd" / "hermes-fleet.service.in"

EXPECTED_ORGANIZATIONS = {
    "operator": (8460, "/operator/"),
    "agentik": (8461, "/agentik/"),
    "mission": (8462, "/mission/"),
    "private": (8463, "/private/"),
}
EXPECTED_DESCRIPTIONS = {
    "operator": "Infrastructure et opérations",
    "agentik": "Organisation et produits",
    "mission": "Missions et espaces clients",
    "private": "Espace personnel isolé",
}


def _typescript_source() -> str:
    sources = sorted((*FRONTEND_SRC.rglob("*.ts"), *FRONTEND_SRC.rglob("*.tsx")))
    assert sources, f"TypeScript frontend sources are missing under {FRONTEND_SRC}"
    return "\n".join(path.read_text(encoding="utf-8") for path in sources)


def _server_source() -> str:
    sources = sorted(SERVER_SRC.rglob("*.ts"))
    assert sources, f"TypeScript server sources are missing under {SERVER_SRC}"
    return "\n".join(path.read_text(encoding="utf-8") for path in sources)


def _organization_records(source: str) -> dict[str, tuple[int, str]]:
    records: dict[str, tuple[int, str]] = {}
    for object_body in re.findall(r"\{([^{}]+)\}", source, flags=re.DOTALL):
        org_match = re.search(
            r"\bid\s*:\s*['\"](operator|agentik|mission|private)['\"]",
            object_body,
        )
        port_match = re.search(r"\bport\s*:\s*(\d+)", object_body)
        path_match = re.search(
            r"\bpath\s*:\s*['\"](/(?:operator|agentik|mission|private)/)['\"]",
            object_body,
        )
        if org_match and port_match and path_match:
            org_id = org_match.group(1)
            assert org_id not in records, f"duplicate organization id: {org_id}"
            records[org_id] = (int(port_match.group(1)), path_match.group(1))
    return records


def test_frontend_is_a_reproducible_typescript_application():
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))

    assert (FRONTEND / "package-lock.json").is_file()
    assert (FRONTEND / "tsconfig.json").is_file()
    assert (FRONTEND / "tsconfig.server.json").is_file()
    assert "typescript" in {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
    assert {"test", "typecheck", "build"} <= package.get("scripts", {}).keys()
    package_scripts = "\n".join(package["scripts"].values())
    assert "tsconfig.server.json" in package_scripts


def test_frontend_declares_exactly_the_four_isolated_organization_dashboards():
    source = _typescript_source()

    assert _organization_records(source) == EXPECTED_ORGANIZATIONS


def test_frontend_switches_organizations_with_same_origin_paths():
    source = _typescript_source()

    assert re.search(r"<button\b", source, flags=re.IGNORECASE)
    assert re.search(r"onClick\s*=|addEventListener\(['\"]click['\"]", source)
    assert "dashboardPath" in source
    assert re.search(r"active|selected|current", source, flags=re.IGNORECASE)

    # Each iframe stays under the fleet shell's origin. This avoids four extra
    # TLS origins and lets the server proxy to the isolated loopback backends.
    assert "window.location.hostname" not in source
    assert not re.search(r"https?://[^`'\"]*:\$?\{?port", source)
    assert "agk-core.tail64d114.ts.net" not in source
    assert not re.search(r"https?://(?:\d{1,3}\.){3}\d{1,3}", source)


def test_frontend_embeds_each_dashboard_and_offers_a_standalone_link():
    source = _typescript_source()

    assert re.search(r"<iframe\b", source, flags=re.IGNORECASE)
    assert re.search(r"<a\b", source, flags=re.IGNORECASE)
    assert re.search(r"target\s*=\s*['\"]_blank['\"]", source)
    assert re.search(r"noopener", source, flags=re.IGNORECASE)


def test_shell_uses_a_local_app_icon_and_private_tailnet_badge():
    source = (FRONTEND_SRC / "main.ts").read_text(encoding="utf-8")

    assert re.search(r"<img\b[^>]*class=['\"]brand-icon['\"]", source)
    assert re.search(r"<img\b[^>]*src=['\"]/hermes-icon\.webp['\"]", source)
    assert "tailnet-badge" in source
    assert "tailnet-label" in source
    assert "Tailnet privé" in source


def test_organization_switcher_keeps_four_described_workspaces_accessible():
    source = (FRONTEND_SRC / "main.ts").read_text(encoding="utf-8")
    organizations = (FRONTEND_SRC / "organisations.ts").read_text(encoding="utf-8")
    styles = (FRONTEND_SRC / "styles.css").read_text(encoding="utf-8")
    trigger = re.search(
        r"<button\b(?=[^>]*organisation-trigger).*?</button>",
        source,
        flags=re.DOTALL,
    )

    assert trigger
    assert 'aria-haspopup="menu"' in trigger.group(0)
    assert 'aria-controls="organisation-menu"' in trigger.group(0)
    assert "data-current-name" in trigger.group(0)
    assert "data-current-description" in trigger.group(0)
    assert "ORGANISATIONS.map" in source
    assert 'class="organisation-option"' in source
    assert 'data-organisation="${organisation.id}"' in source
    assert "${organisation.description}" in source
    for org_id, description in EXPECTED_DESCRIPTIONS.items():
        assert f'id: "{org_id}"' in organizations
        assert f'description: "{description}"' in organizations

    # Responsive layouts may reshape the trigger but must not remove it.
    assert not re.search(
        r"\.organisation-trigger[^{}]*\{[^{}]*display\s*:\s*none",
        styles,
        flags=re.DOTALL,
    )


def test_installable_metadata_and_icons_are_local_files():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    expected_links = {
        "icon": "/favicon-32.png",
        "apple-touch-icon": "/apple-touch-icon.png",
        "manifest": "/site.webmanifest",
    }

    for relation, href in expected_links.items():
        assert re.search(
            rf"<link\b(?=[^>]*rel=['\"]{relation}['\"])(?=[^>]*href=['\"]{re.escape(href)}['\"])[^>]*>",
            html,
        )

    assets = {
        "hermes-icon.webp": b"RIFF",
        "favicon-32.png": b"\x89PNG\r\n\x1a\n",
        "apple-touch-icon.png": b"\x89PNG\r\n\x1a\n",
        "app-icon-192.png": b"\x89PNG\r\n\x1a\n",
        "app-icon-512.png": b"\x89PNG\r\n\x1a\n",
    }
    for filename, signature in assets.items():
        content = (FRONTEND_PUBLIC / filename).read_bytes()
        assert content.startswith(signature), f"invalid local app asset: {filename}"
        assert len(content) > 32, f"empty local app asset: {filename}"
        if filename.endswith(".webp"):
            assert content[8:12] == b"WEBP"

    manifest = json.loads(
        (FRONTEND_PUBLIC / "site.webmanifest").read_text(encoding="utf-8")
    )
    assert manifest.get("start_url") == "/"
    assert manifest.get("display") == "standalone"
    assert {icon["src"] for icon in manifest.get("icons", [])} == {
        "/app-icon-192.png",
        "/app-icon-512.png",
    }


def test_shell_runtime_has_no_external_asset_or_network_urls():
    runtime_files = [
        FRONTEND / "index.html",
        FRONTEND_SRC / "main.ts",
        FRONTEND_SRC / "organisations.ts",
        FRONTEND_SRC / "styles.css",
        FRONTEND_PUBLIC / "site.webmanifest",
    ]

    for path in runtime_files:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"(?:https?:)?//", source), (
            f"external runtime URL found in {path.relative_to(ROOT)}"
        )


def test_shell_respects_responsive_and_reduced_motion_preferences():
    styles = (FRONTEND_SRC / "styles.css").read_text(encoding="utf-8")

    assert re.search(r"@media\s*\([^)]*max-width\s*:\s*760px", styles)
    assert re.search(r"@media\s*\([^)]*max-width\s*:\s*430px", styles)
    assert re.search(r"@media\s*\(prefers-reduced-motion\s*:\s*reduce\)", styles)
    assert re.search(r"animation-duration\s*:\s*0\.01ms", styles)
    assert re.search(r"transition-duration\s*:\s*0\.01ms", styles)


def test_fleet_shell_uses_a_rounded_linear_first_dashboard_frame():
    styles = (FRONTEND_SRC / "styles.css").read_text(encoding="utf-8")
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "--panel-radius: 0.75rem" in styles
    assert re.search(
        r"\.dashboard-stage\s*\{[^}]*padding\s*:\s*10px 12px 12px",
        styles,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.dashboard-frame\s*\{[^}]*border-radius\s*:\s*var\(--panel-radius\)",
        styles,
        flags=re.DOTALL,
    )
    assert 'name="color-scheme" content="dark light"' in html


def test_compiled_typescript_server_proxies_all_prefixes_to_loopback():
    source = _server_source()

    assert "ORGANISATIONS" in source
    assert "127.0.0.1" in source
    assert "8459" in source
    assert re.search(r"createServer|serve\(", source)
    assert re.search(r"listen\(", source)
    assert re.search(r"proxy|upstream", source, flags=re.IGNORECASE)
    assert re.search(r"ORGANISATIONS\.map\(", source)
    assert "organisation.path" in source
    assert "organisation.port" in source
    assert "0.0.0.0" not in source
    for port, path in EXPECTED_ORGANIZATIONS.values():
        # The server derives paths and ports from the shared organization table.
        assert str(port) in _typescript_source()
        assert path in _typescript_source()


def test_installer_runs_dashboard_processes_on_loopback_only():
    installer = INSTALLER.read_text(encoding="utf-8")
    service = HERMES_SERVICE_TEMPLATE.read_text(encoding="utf-8")
    combined = f"{installer}\n{service}"

    assert "hermes dashboard" in combined
    assert not re.search(r"\bhermes\s+serve\b", combined)
    assert "127.0.0.1" in combined
    assert not re.search(r"--host\s+0\.0\.0\.0", combined)
    assert re.search(r'expected_address=["\']127\.0\.0\.1:\$port["\']', installer)
    assert re.search(r"\$4\s*==\s*address", installer)
    for org_id, (port, _path) in EXPECTED_ORGANIZATIONS.items():
        assert org_id in installer
        assert str(port) in combined


def test_installer_publishes_only_the_central_tailscale_https_route():
    installer = INSTALLER.read_text(encoding="utf-8")
    lowered = installer.lower()

    assert re.search(r"tailscale\s+serve\b", installer)
    assert re.search(r"--https(?:=|\s+)443\b", installer)
    assert "http://127.0.0.1:8459" in installer
    assert re.search(r"ports=\(8460 8461 8462 8463\)", installer)

    # Old per-profile Serve routes may be removed only by exact port. The
    # prior JSON validation proves ownership before the scoped port is
    # removed. They must never be recreated or removed with a global reset.
    cleanup = re.search(
        r'tailscale\s+serve[^\n]*--https=["\']?\$port["\']?\s+off\b',
        installer,
    )
    assert cleanup
    validation = re.search(
        r'validate_serve_config\s+["\']?\$serve_before["\']?\s+before', installer
    )
    assert validation
    assert validation.start() < cleanup.start()
    assert not re.search(
        r'tailscale\s+serve[^\n]*--https=["\']?\$port["\']?[^\n]*'
        r'http://127\.0\.0\.1:\$port',
        installer,
        flags=re.MULTILINE,
    )
    assert re.search(
        r'validate_serve_config\s+["\']?\$serve_after["\']?\s+after', installer
    )
    assert "legacy Serve route remains" in installer
    assert not re.search(r"^\s*tailscale\s+funnel\b", lowered, flags=re.MULTILINE)
    assert not re.search(
        r"^\s*tailscale\s+serve\s+reset\b", lowered, flags=re.MULTILINE
    )


def test_four_dashboard_services_restart_and_remain_profile_owned():
    installer = INSTALLER.read_text(encoding="utf-8")
    service = HERMES_SERVICE_TEMPLATE.read_text(encoding="utf-8")

    assert re.search(r"^Restart=always$", service, flags=re.MULTILINE)
    assert re.search(r"^UMask=0077$", service, flags=re.MULTILINE)
    assert re.search(r"^NoNewPrivileges=true$", service, flags=re.MULTILINE)
    assert "User=root" not in service
    assert ".config/systemd/user" in installer
    assert re.search(r"install\b[^\n]*\s-o\s+['\"]?\$?\{?profile_user", installer)
    assert re.search(r"sudo\s+-u\s+['\"]?\$?\{?profile_user", installer)
    assert re.search(r"systemctl\s+--user\s+restart\s+hermes-serve\.service", installer)


def test_central_fleet_service_is_loopback_only_and_restartable():
    installer = INSTALLER.read_text(encoding="utf-8")
    service = FLEET_SERVICE_TEMPLATE.read_text(encoding="utf-8")

    assert "hermes-fleet.service" in installer
    assert "127.0.0.1" in service
    assert "8459" in service
    assert "server-dist/server.js" in service
    assert re.search(r"^Restart=always$", service, flags=re.MULTILINE)
    assert re.search(r"^UMask=0077$", service, flags=re.MULTILINE)
    assert re.search(r"^NoNewPrivileges=true$", service, flags=re.MULTILINE)
    assert "User=root" not in service
    assert "/home/operator/.config/systemd/user" in installer
    assert re.search(r"install\b[^\n]*\s-o\s+operator\b", installer)
    assert re.search(r"systemctl\s+--user\s+restart\s+hermes-fleet\.service", installer)


def test_main_installer_requires_an_explicit_system_fleet_opt_in():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "--with-hermes-fleet" in source
    assert re.search(r"--with-hermes-fleet\).*?=true", source)
    assert "install-hermes-fleet-dashboard.sh" in source
    assert re.search(
        r"install_hermes_fleet.*system_install|system_install.*install_hermes_fleet",
        source,
        flags=re.DOTALL,
    )
