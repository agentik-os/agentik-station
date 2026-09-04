from __future__ import annotations

from pathlib import Path

import agentik_station.cli as cli

ROOT = Path(__file__).resolve().parents[2]


def test_versions_lock_pins_hermes_and_deps():
    lock = (ROOT / "config" / "versions.lock").read_text()
    for pin in (
        "HERMES_RELEASE=v2026.8.31",
        "HERMES_COMMIT=29112bef099274229cadff79cdff7bf7b99c4b77",
        "HERMES_INSTALL_SHA256=5854b15670b51a8daae8f59ddfa917062de9f74be261eb73b4b8d719710f8968",
        "PYTHON_VERSION=3.14.7",
        "AI_PYTHON_VERSION=3.13.15",
        "NODE_VERSION=24.20.0",
        "GITHUB_CLI_VERSION=2.100.0",
        "VERCEL_CLI_VERSION=59.11.2",
        "CODEX_CLI_VERSION=0.153.2",
        "COMPOSIO_CLI_VERSION=0.4.0",
        "COMPOSIO_INSTALL_SHA256=7a63922b75d206d16c790cdf683edac23f536903a28e13e94bfe3e55690b7a63",
        "DISCORD_JS_VERSION=14.27.0",
        "DISCORD_JS_INTEGRITY=sha512-qHbFlFG2N7y3LjPySYsL6A1+BnX6bkTVgo842EX0CqVPk/KTMwZkojPHEXKsQUpWZNyz5BISNHK1cPpQw0+m4A==",
        "SHADCN_CLI_VERSION=4.21.0",
        "SHADCN_CLI_INTEGRITY=sha512-UU2mFNusW8C5rvadKdH69vERYZqUlOOlXBcf0MYhYLdTGP6DPti7X4qovCu+RTfCqsAgq/T+YfE0Vnttxh9aiw==",
        "NEXTJS_VERSION=16.3.4",
        "CONVEX_VERSION=1.45.0",
        "CLERK_NEXTJS_VERSION=7.9.1",
        "STRIPE_NODE_VERSION=22.6.1",
        "LUCIDE_REACT_VERSION=1.41.0",
        "LANGFUSE_RELEASE=v4.28.1",
        "CRAWL4AI_PYTHON_VERSION=0.9.3",
        "PONYTAIL_RELEASE=v4.9.0",
        "PONYTAIL_COMMIT=0a4dd63ad4541f4f655c4108a295916f3c1d8fda",
        "PARAKEET_RELEASE=v0.8.0",
        "PARAKEET_COMMIT=436daa8a75fa8c6d115a3188e18ef046444edccf",
        "PARAKEET_IMAGE=ghcr.io/achetronic/parakeet@sha256:00f8a02ec0ca6a7d6d5ee9f959060d8498b14f741a25e914941d22547a3f37f4",
        "OPENAI_STT_MODEL=gpt-transcribe",
        "OPENAI_TTS_MODEL=gpt-4o-mini-tts",
        "TAILSCALE_MIN_VERSION=1.102.3",
        "TAILSCALE_APT_KEY_SHA256=3e03dacf222698c60b8e2f990b809ca1b3e104de127767864284e6c228f1fb39",
    ):
        assert pin in lock


def test_deps_stack_yaml_exists():
    stack = (ROOT / "config" / "deps" / "stack.yaml").read_text()
    for name in ("discord-js-sdk", "ponytail", "langfuse", "honcho", "hindsight", "tigervnc", "crawl4ai", "parakeet"):
        assert name in stack


def test_voice_defaults_and_parakeet_service_are_fail_closed():
    voice = (ROOT / "config" / "hermes" / "voice.default.yaml").read_text()
    unit = (ROOT / "runtime" / "systemd" / "station-parakeet.service").read_text()
    assert "provider: openai" in voice
    assert "model: gpt-transcribe" in voice
    assert "model: gpt-4o-mini-tts" in voice
    assert "station-parakeet-transcribe" in voice
    assert "--publish=127.0.0.1:5092:5092" in unit
    assert "--pull=never" in unit
    assert "--cap-drop=all" in unit
    assert "sha256:00f8a02ec0ca6a7d6d5ee9f959060d8498b14f741a25e914941d22547a3f37f4" in unit


def test_hermes_update_and_deps_scripts_executable():
    for rel in (
        "scripts/station_hermes_update.sh",
        "scripts/station_deps_install.sh",
        "scripts/station_toolchain_install.sh",
        "scripts/station_parakeet_transcribe.sh",
        "scripts/station_guided_setup_enable.sh",
        "scripts/ci_vps_acceptance.sh",
        "scripts/generate_release_metadata.py",
    ):
        path = ROOT / rel
        assert path.is_file()
        assert path.stat().st_mode & 0o111


def test_ponytail_install_uses_immutable_hermes_plugin_ref():
    script = (ROOT / "scripts" / "station_deps_install.sh").read_text()
    assert 'plugins install "$PONYTAIL_REPOSITORY" --ref "$PONYTAIL_COMMIT" --enable' in script


def test_catalog_includes_new_modules():
    import json
    catalog = json.loads((ROOT / "modules" / "catalog.json").read_text())
    ids = {m["id"] for m in catalog["modules"]}
    for mid in ("hermes-platforms", "resource-catalog", "ponytail", "langfuse", "honcho", "hindsight", "crawl4ai", "parakeet", "tigervnc"):
        assert mid in ids


def test_cli_registers_deps_and_hermes_update():
    parser = cli.build_parser()
    parser.parse_args(["hermes", "update", "--check-only"])
    parser.parse_args(["deps", "list"])
    parser.parse_args(["deps", "platforms"])
    parser.parse_args(["deps", "toolchain-plan"])
    parser.parse_args(["deps", "toolchain-check"])
    parser.parse_args(["platform", "setup", "--zone", "organization-alpha-dev", "--platform", "slack", "--plan"])
    parser.parse_args(["resource", "list"])
    parser.parse_args(["resource", "stack-plan", "--id", "web-product"])
    parser.parse_args(["rules", "install", "--repo", "/tmp/example", "--plan"])
    parser.parse_args(["client", "doctor", "organization-alpha"])
    parser.parse_args(["provider", "composio-discord", "plan", "--zone", "organization-alpha-dev"])
    parser.parse_args([
        "setup-link", "create",
        "--state-root", "/var/lib/station/zones/discord-bootstrap/connector-state/setup-links",
        "--base-url", "https://station.example.ts.net/station-setup",
        "--zone", "discord-bootstrap",
        "--principal", "discord-123456789",
        "--provider", "openai",
        "--purpose", "station-secret",
    ])
