from __future__ import annotations

import pytest

from agentik_station.errors import ValidationError
from agentik_station.identifiers import (
    normalize_deploy_environment,
    validate_identifier,
    validate_remote_target,
)


@pytest.mark.parametrize(
    "value",
    ["organization-alpha", "station-core-01", "project9", "a"],
)
def test_identifier_accepts_canonical_values(value: str) -> None:
    assert validate_identifier(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "../escape",
        "../../escape",
        "organization-alpha/prod",
        "Example Client",
        "-organization-alpha",
        "organization-alpha-",
        "moon base",
        "organization-alpha;touch-pwn",
        "ｍoonbase",
        "équipe",
        "a" * 49,
    ],
)
def test_identifier_rejects_traversal_shell_unicode_and_ambiguous_values(value: str) -> None:
    with pytest.raises(ValidationError):
        validate_identifier(value)


def test_remote_target_defaults_to_strict_valid_destination() -> None:
    target = validate_remote_target("operator@organization-alpha-prod-01", 2222)
    assert target.destination == "operator@organization-alpha-prod-01"
    assert target.port == 2222


@pytest.mark.parametrize(
    "target",
    [
        "operator@host;touch /tmp/pwn",
        "operator@host$(id)",
        "-oProxyCommand=id",
        "operator@@host",
        "operator@host name",
        "operator@bad_host!",
    ],
)
def test_remote_target_rejects_command_and_option_injection(target: str) -> None:
    with pytest.raises(ValidationError):
        validate_remote_target(target)


def test_client_project_environment_is_explicit() -> None:
    assert normalize_deploy_environment("dev") == "development"
    assert normalize_deploy_environment("prod") == "production"
    with pytest.raises(ValidationError):
        normalize_deploy_environment("lab")
