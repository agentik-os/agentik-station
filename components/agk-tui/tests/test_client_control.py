import hashlib
import hmac
import importlib.util
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "agk_client_control", ROOT / "scripts" / "client_control.py"
)
assert SPEC and SPEC.loader
client_control = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = client_control
SPEC.loader.exec_module(client_control)


def init_args(slug="test-client", **overrides):
    values = {
        "slug": slug,
        "name": "Test Client",
        "runtime": "hybrid",
        "github_mode": "org",
        "github_org": "test-org",
        "linear_workspace": "workspace-id",
        "linear_team": "team-id",
        "discord_mode": "shared-command-center",
        "discord_guild": "123456789012345678",
        "dry_run": False,
    }
    values.update(overrides)
    return Namespace(**values)


@pytest.fixture
def layout(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AGK_CLIENT", raising=False)
    monkeypatch.delenv("AGK_CONTROL_HOME", raising=False)
    monkeypatch.delenv("AGK_CLIENT_DIR", raising=False)
    monkeypatch.setenv("AGK_CLIENT_WORKSPACE", str(home / "workspace"))
    monkeypatch.setenv("AGK_TERMINAL_ROOT", str(ROOT))
    return client_control.Layout.current()


def declare_repository(layout, slug, repository="test-org/product"):
    path = layout.client(slug) / ".client" / "integrations.yaml"
    value = client_control.yaml_document(path)
    value["github"]["repositories"] = [repository]
    client_control.atomic_yaml(path, value)
    return repository


def make_work(layout, slug="test-client"):
    repository = declare_repository(layout, slug)
    record = client_control.create_work(
        layout,
        Namespace(
            slug=slug,
            issue="FOU-142",
            title="Attachment classification",
            role="backend-engineer",
            provider="hermes",
            repo=repository,
            branch=None,
            session=None,
            target="staging",
        ),
    )
    path, record = client_control.load_work(layout, slug, record["id"])
    integrations_path = layout.client(slug) / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(integrations_path)
    integrations["linear"]["delivery_project_id"] = "project-id"
    integrations["discord"].update(
        {
            "owner_user_id": "test-owner",
            "guild_id": "123456789012345678",
            "channels": {"dev_requests": "123456789012345679"},
        }
    )
    client_control.atomic_yaml(integrations_path, integrations)
    attach_verified_linear_snapshot(layout, slug, record, "FOU-142")
    authorization = {
        "id": "discord:999",
        "actor": "test-owner",
        "actor_id": "test-owner",
        "source": "discord",
        "timestamp": "2026-08-27T00:00:00+00:00",
        "channel_id": "123456789012345679",
        "message_id": "999",
        "guild_id": "123456789012345678",
        "client": slug,
        "project": "project-id",
        "issue": "FOU-142",
        "scope": record["title"],
        "priority": "unspecified",
        "constraints": [],
        "at": "2026-08-27T00:00:00+00:00",
        "message_sha256": hashlib.sha256(b"START FOU-142").hexdigest(),
        "message_timestamp": "2026-08-27T00:00:00+00:00",
    }
    payload = {"work_id": record["id"], **authorization}
    payload.pop("client", None)
    authorization["receipt"] = client_control.write_start_authorization_receipt(
        layout, slug, record["id"], payload
    )
    record["authorization"] = authorization
    record["status"] = "in_progress"
    client_control.atomic_yaml(path, record)
    return record


def attach_verified_linear_snapshot(layout, slug, record, issue):
    snapshot = {
        "identifier": issue,
        "title": record["title"],
        "description": "Authoritative Linear description",
        "updated_at": "2026-08-27T12:00:00.000Z",
        "team_id": "team-id",
        "comments": [],
        "attachments": [],
        "relations": [],
        "state": {},
        "id": None,
        "url": None,
    }
    body = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    relative = Path("state") / "work" / f"{record['id']}.linear-snapshot.json"
    client_control.atomic_text(
        layout.client(slug) / relative,
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        0o600,
    )
    receipt = client_control.write_linear_snapshot_receipt(
        layout,
        slug,
        record["id"],
        issue=issue,
        team_id="team-id",
        snapshot_sha256=hashlib.sha256(body.encode()).hexdigest(),
        updated_at=snapshot["updated_at"],
    )
    record["context"] = {
        "complete": True,
        "fields": {
            "documented": True,
            "requested_outcome": record["title"],
            "security_and_data_constraints": [],
        },
        "linear_snapshot": {
            "identifier": issue,
            "team_id": "team-id",
            "updated_at": snapshot["updated_at"],
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
            "path": str(relative),
            "receipt": receipt,
        },
    }
    return record


def test_work_context_requires_complete_client_scoped_contract(layout, monkeypatch):
    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client", issue="FOU-144", title="Context contract",
            role="backend-engineer", provider="hermes", repo=repository,
            branch=None, session=None, target="staging",
        ),
    )
    workflow = client_control.yaml_document(
        layout.client("test-client") / ".client" / "workflow.yaml"
    )
    fields = {
        key: ["evidence"] if key in {"attachments_and_screenshots", "acceptance_criteria", "dependencies", "test_plan", "real_navigation_requirements", "staging_and_deployment_requirements", "evidence_plan", "links_to_source_mission_pr_release_incident_and_decisions", "risks"} else "documented"
        for key in workflow["intake"]["product_definition_requires"]
    }
    context_file = layout.client("test-client") / "tmp" / "context.yaml"
    client_control.atomic_yaml(context_file, fields)
    monkeypatch.setattr(
        client_control,
        "composio_execute",
        lambda tool, account, data: {
            "data": {
                "issue": {
                    "identifier": "FOU-144",
                    "title": "Context contract",
                    "description": "Authoritative Linear description",
                    "updatedAt": "2026-08-27T12:00:00.000Z",
                    "url": "https://linear.app/test/issue/FOU-144",
                    "team": {"id": "team-id"},
                    "comments": {"nodes": [{"id": "comment-1", "body": "History"}]},
                    "attachments": {"nodes": [{"id": "attachment-1", "title": "Capture"}]},
                    "relations": {"nodes": []},
                }
            }
        },
    )

    outside = layout.workspace / "outside.yaml"
    client_control.atomic_yaml(outside, fields)
    with pytest.raises(client_control.ClientError, match="inside the client boundary"):
        client_control.update_work_context(
            layout,
            Namespace(
                slug="test-client", work_id=work["id"], actor="pm",
                context_file=str(outside),
            ),
        )

    updated = client_control.update_work_context(
        layout,
        Namespace(
            slug="test-client", work_id=work["id"], actor="pm",
            context_file=str(context_file),
        ),
    )

    assert updated["context"]["complete"] is True
    assert set(fields) <= set(updated["context"]["fields"])
    assert updated["context"]["linear_snapshot"]["identifier"] == "FOU-144"
    assert len(updated["context"]["linear_snapshot"]["sha256"]) == 64
    receipt = layout.system / updated["context"]["linear_snapshot"]["receipt"]
    assert receipt.is_file()
    assert receipt.stat().st_mode & 0o777 == 0o400
    assert len(client_control.yaml_document(receipt)["signature"]) == 64
    snapshot = (
        layout.client("test-client")
        / updated["context"]["linear_snapshot"]["path"]
    )
    assert snapshot.is_file()
    assert client_control.yaml_document(snapshot)["description"] == (
        "Authoritative Linear description"
    )


def test_work_context_cannot_be_refinalized_after_signed_snapshot(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "backlog"
    client_control.atomic_yaml(path, record)
    context_file = layout.client("test-client") / "tmp" / "replacement.yaml"
    client_control.atomic_yaml(context_file, {"replacement": "attempt"})

    with pytest.raises(client_control.ClientError, match="already finalized"):
        client_control.update_work_context(
            layout,
            Namespace(
                slug="test-client",
                work_id=work["id"],
                actor="pm",
                context_file=str(context_file),
            ),
        )


def test_concurrent_context_finalization_cannot_corrupt_signed_snapshot(
    layout, monkeypatch
):
    import threading

    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client",
            issue="FOU-143",
            title="Concurrent context",
            role="backend-engineer",
            provider="hermes",
            repo=repository,
            branch=None,
            session=None,
            target="staging",
        ),
    )
    workflow = client_control.yaml_document(
        layout.client("test-client") / ".client" / "workflow.yaml"
    )
    fields = {
        key: ["evidence"]
        if key
        in {
            "attachments_and_screenshots",
            "acceptance_criteria",
            "dependencies",
            "test_plan",
            "real_navigation_requirements",
            "staging_and_deployment_requirements",
            "evidence_plan",
            "links_to_source_mission_pr_release_incident_and_decisions",
            "risks",
        }
        else "documented"
        for key in workflow["intake"]["product_definition_requires"]
    }
    context_file = layout.client("test-client") / "tmp" / "concurrent.yaml"
    client_control.atomic_yaml(context_file, fields)
    start = threading.Event()

    def snapshot(marker):
        return {
            "identifier": "FOU-143",
            "title": "Concurrent context",
            "description": marker,
            "url": "https://linear.app/test/issue/FOU-143",
            "updated_at": (
                "2026-08-27T12:00:01Z"
                if marker == "second"
                else "2026-08-27T12:00:00Z"
            ),
            "team_id": "team-id",
            "comments": [],
            "attachments": [],
            "relations": [],
        }

    monkeypatch.setattr(
        client_control,
        "authoritative_linear_snapshot",
        lambda *_: snapshot(threading.current_thread().name),
    )
    errors = []
    completed = []

    def finalize(actor):
        assert start.wait(5)
        try:
            completed.append(
                client_control.update_work_context(
                    layout,
                    Namespace(
                        slug="test-client",
                        work_id=work["id"],
                        actor=actor,
                        context_file=str(context_file),
                    ),
                )
            )
        except client_control.ClientError as error:
            errors.append(error)

    threads = [
        threading.Thread(target=finalize, args=(actor,), name=actor)
        for actor in ("first", "second")
    ]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert len(completed) == 1
    assert len(errors) == 1

    _, record = client_control.load_work(layout, "test-client", work["id"])
    snapshot_path = layout.client("test-client") / record["context"]["linear_snapshot"][
        "path"
    ]
    snapshot_body = json.dumps(
        client_control.yaml_document(snapshot_path),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert hashlib.sha256(snapshot_body.encode()).hexdigest() == record["context"][
        "linear_snapshot"
    ]["sha256"]


def test_context_finalization_cannot_overwrite_concurrent_transition(
    layout, monkeypatch
):
    import threading

    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client",
            issue="FOU-144",
            title="Transition race",
            role="backend-engineer",
            provider="hermes",
            repo=repository,
            branch=None,
            session=None,
            target="staging",
        ),
    )
    workflow = client_control.yaml_document(
        layout.client("test-client") / ".client" / "workflow.yaml"
    )
    fields = {
        key: ["evidence"]
        if key
        in {
            "attachments_and_screenshots",
            "acceptance_criteria",
            "dependencies",
            "test_plan",
            "real_navigation_requirements",
            "staging_and_deployment_requirements",
            "evidence_plan",
            "links_to_source_mission_pr_release_incident_and_decisions",
            "risks",
        }
        else "documented"
        for key in workflow["intake"]["product_definition_requires"]
    }
    context_file = layout.client("test-client") / "tmp" / "transition-race.yaml"
    client_control.atomic_yaml(context_file, fields)
    monkeypatch.setattr(
        client_control,
        "authoritative_linear_snapshot",
        lambda *_: {
            "identifier": "FOU-144",
            "title": "Transition race",
            "description": "authoritative",
            "url": "https://linear.app/test/issue/FOU-144",
            "updated_at": "2026-08-27T12:00:00Z",
            "team_id": "team-id",
            "comments": [],
            "attachments": [],
            "relations": [],
        },
    )
    transition_writing = threading.Event()
    release_transition = threading.Event()
    original_atomic_yaml = client_control.atomic_yaml
    work_path, _ = client_control.load_work(layout, "test-client", work["id"])

    def blocking_atomic_yaml(path, data, mode=0o600):
        if (
            threading.current_thread().name == "blocking-transition"
            and path == work_path
        ):
            transition_writing.set()
            assert release_transition.wait(5)
        return original_atomic_yaml(path, data, mode)

    monkeypatch.setattr(client_control, "atomic_yaml", blocking_atomic_yaml)
    transition_errors = []
    finalization_errors = []

    def transition():
        try:
            client_control.transition_work(
                layout, "test-client", work["id"], "blocked", actor="supervisor"
            )
        except client_control.ClientError as error:
            transition_errors.append(error)

    def finalize():
        try:
            client_control.update_work_context(
                layout,
                Namespace(
                    slug="test-client",
                    work_id=work["id"],
                    actor="product",
                    context_file=str(context_file),
                ),
            )
        except client_control.ClientError as error:
            finalization_errors.append(error)

    transition_thread = threading.Thread(
        target=transition, name="blocking-transition"
    )
    transition_thread.start()
    assert transition_writing.wait(5)
    finalization_thread = threading.Thread(target=finalize, name="finalizer")
    finalization_thread.start()
    finalization_thread.join(1)
    release_transition.set()
    transition_thread.join(5)
    finalization_thread.join(5)
    assert not transition_thread.is_alive()
    assert not finalization_thread.is_alive()
    assert not transition_errors
    assert finalization_errors

    _, record = client_control.load_work(layout, "test-client", work["id"])
    assert record["status"] == "blocked"
    assert record["context"]["complete"] is False


def test_evidence_update_preserves_concurrent_status_transition(layout, monkeypatch):
    import threading

    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, _ = client_control.load_work(layout, "test-client", work["id"])
    transition_writing = threading.Event()
    release_transition = threading.Event()
    original_atomic_yaml = client_control.atomic_yaml

    def blocking_atomic_yaml(path, data, mode=0o600):
        if (
            threading.current_thread().name == "blocking-transition"
            and path == work_path
        ):
            transition_writing.set()
            assert release_transition.wait(5)
        return original_atomic_yaml(path, data, mode)

    monkeypatch.setattr(client_control, "atomic_yaml", blocking_atomic_yaml)
    errors = []

    def transition():
        try:
            client_control.transition_work(
                layout, "test-client", work["id"], "blocked", actor="supervisor"
            )
        except client_control.ClientError as error:
            errors.append(error)

    def update():
        try:
            client_control.update_evidence(
                layout,
                Namespace(
                    slug="test-client", work_id=work["id"], actor="qa",
                    pull_request=None, commit=None, engineering_review=None,
                    ci=None, qa=None, security=None, security_decision_id=None,
                    preview=None, staging_build=None, screenshot=[],
                    validation_step=[], browser_report=None, qa_session_id=None,
                    rollback_plan=None, risk="concurrent-risk",
                    production_health=None, linear_done=False,
                    linear_attachment=[],
                ),
            )
        except client_control.ClientError as error:
            errors.append(error)

    transition_thread = threading.Thread(
        target=transition, name="blocking-transition"
    )
    transition_thread.start()
    assert transition_writing.wait(5)
    update_thread = threading.Thread(target=update, name="evidence-updater")
    update_thread.start()
    update_thread.join(1)
    release_transition.set()
    transition_thread.join(5)
    update_thread.join(5)
    assert not transition_thread.is_alive()
    assert not update_thread.is_alive()
    assert not errors

    _, record = client_control.load_work(layout, "test-client", work["id"])
    assert record["status"] == "blocked"
    assert record["evidence"]["risk"] == "concurrent-risk"
    assert record["events"][-1]["event"] == "work.evidence_updated"


def test_start_authorization_rejects_stale_discord_message():
    with pytest.raises(client_control.ClientError, match="freshness window"):
        client_control.validate_start_message_freshness(
            "2026-08-27T17:00:00+00:00",
            now=client_control.dt.datetime.fromisoformat("2026-08-27T18:00:01+00:00"),
        )


def test_start_authorization_message_cannot_be_reused_for_another_work(layout):
    client_control.create_client(layout, init_args())
    _first = make_work(layout)
    second = client_control.create_work(
        layout,
        Namespace(
            slug="test-client",
            issue="FOU-142",
            title="Second work record",
            role="backend-engineer",
            provider="hermes",
            repo="test-org/product",
            branch=None,
            session=None,
            target="staging",
        ),
    )

    with pytest.raises(
        client_control.ClientError, match="already authorized another work"
    ):
        client_control.ensure_start_message_unused(
            layout, "test-client", "999", second["id"]
        )


def test_start_authorization_message_cannot_be_reused_across_clients(layout):
    client_control.create_client(layout, init_args())
    make_work(layout)
    other = init_args()
    other.slug = "other-client"
    other.name = "Other Client"
    client_control.create_client(layout, other)

    with pytest.raises(client_control.ClientError, match="already authorized"):
        client_control.ensure_start_message_unused(
            layout, "other-client", "999", "WORK-OTHER"
        )


def test_ready_authorization_is_derived_from_verified_discord_message(layout, monkeypatch):
    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["linear"]["delivery_project_id"] = "project-id"
    integrations["discord"].update(
        {
            "enabled": True,
            "guild_id": "123456789012345678",
            "owner_user_id": "42",
            "channels": {"dev_requests": "123456789012345679"},
            "token_set": True,
        }
    )
    client_control.atomic_yaml(config_path, integrations)
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client", issue="FOU-145", title="Authorized work",
            role="backend-engineer", provider="hermes", repo=repository,
            branch=None, session=None, target="staging",
        ),
    )
    path, record = client_control.load_work(layout, "test-client", work["id"])
    attach_verified_linear_snapshot(layout, "test-client", record, "FOU-145")
    client_control.atomic_yaml(path, record)

    def fake_get(_layout, _slug, endpoint):
        if endpoint == "/channels/123456789012345679":
            return {"id": "123456789012345679", "guild_id": "123456789012345678"}
        if endpoint == "/channels/123456789012345679/messages/999":
            return {
                "id": "999", "channel_id": "123456789012345679",
                "content": "START FOU-145",
                "timestamp": client_control.dt.datetime.now(
                    client_control.dt.timezone.utc
                ).isoformat(),
                "author": {"id": "42", "bot": False},
            }
        raise AssertionError(endpoint)

    monkeypatch.setattr(client_control, "discord_client_get", fake_get)
    ready = client_control.authorize_work_start(
        layout,
        Namespace(
            slug="test-client", work_id=work["id"],
            channel_id="123456789012345679", message_id="999",
        ),
    )

    assert ready["status"] == "todo"
    assert ready["authorization"]["actor_id"] == "42"
    assert ready["authorization"]["source"] == "discord"
    assert ready["authorization"]["id"] == "discord:999"
    assert ready["authorization"]["receipt"].startswith("audit/start-authorizations/")

    path, forged = client_control.load_work(layout, "test-client", work["id"])
    forged["authorization"]["message_id"] = "1000"
    forged["authorization"]["id"] = "discord:1000"
    client_control.atomic_yaml(path, forged)
    with pytest.raises(client_control.ClientError, match="START receipt"):
        client_control.transition_work(
            layout, "test-client", work["id"], "in_progress", actor="attacker"
        )


def test_start_authorization_cannot_overwrite_concurrent_transition(
    layout, monkeypatch
):
    import threading

    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["linear"]["delivery_project_id"] = "project-id"
    integrations["discord"].update(
        {
            "enabled": True,
            "guild_id": "123456789012345678",
            "owner_user_id": "42",
            "channels": {"dev_requests": "123456789012345679"},
            "token_set": True,
        }
    )
    client_control.atomic_yaml(config_path, integrations)
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client", issue="FOU-146", title="Authorization race",
            role="backend-engineer", provider="hermes", repo=repository,
            branch=None, session=None, target="staging",
        ),
    )
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    attach_verified_linear_snapshot(layout, "test-client", record, "FOU-146")
    client_control.atomic_yaml(work_path, record)

    def fake_get(_layout, _slug, endpoint):
        if endpoint == "/channels/123456789012345679":
            return {"id": "123456789012345679", "guild_id": "123456789012345678"}
        if endpoint == "/channels/123456789012345679/messages/1000":
            return {
                "id": "1000", "channel_id": "123456789012345679",
                "content": "START FOU-146",
                "timestamp": client_control.dt.datetime.now(
                    client_control.dt.timezone.utc
                ).isoformat(),
                "author": {"id": "42", "bot": False},
            }
        raise AssertionError(endpoint)

    monkeypatch.setattr(client_control, "discord_client_get", fake_get)
    transition_writing = threading.Event()
    release_transition = threading.Event()
    original_atomic_yaml = client_control.atomic_yaml

    def blocking_atomic_yaml(path, data, mode=0o600):
        if (
            threading.current_thread().name == "blocking-transition"
            and path == work_path
        ):
            transition_writing.set()
            assert release_transition.wait(5)
        return original_atomic_yaml(path, data, mode)

    monkeypatch.setattr(client_control, "atomic_yaml", blocking_atomic_yaml)
    transition_errors = []
    authorization_errors = []

    def transition():
        try:
            client_control.transition_work(
                layout, "test-client", work["id"], "blocked", actor="supervisor"
            )
        except client_control.ClientError as error:
            transition_errors.append(error)

    def authorize():
        try:
            client_control.authorize_work_start(
                layout,
                Namespace(
                    slug="test-client", work_id=work["id"],
                    channel_id="123456789012345679", message_id="1000",
                ),
            )
        except client_control.ClientError as error:
            authorization_errors.append(error)

    transition_thread = threading.Thread(
        target=transition, name="blocking-transition"
    )
    transition_thread.start()
    assert transition_writing.wait(5)
    authorization_thread = threading.Thread(target=authorize, name="authorizer")
    authorization_thread.start()
    authorization_thread.join(1)
    release_transition.set()
    transition_thread.join(5)
    authorization_thread.join(5)
    assert not transition_thread.is_alive()
    assert not authorization_thread.is_alive()
    assert not transition_errors
    assert authorization_errors

    _, final_record = client_control.load_work(layout, "test-client", work["id"])
    assert final_record["status"] == "blocked"
    assert final_record.get("authorization") is None


@pytest.mark.parametrize(
    "unauthorized_content",
    [
        "START FOU-145",
        "GO FOU-14",
        "LAUNCH FOU-14",
        "start FOU-14",
        "START fou-14",
        " START FOU-14",
        "START FOU-14 ",
        "START  FOU-14",
        "START\tFOU-14",
    ],
)
def test_ready_authorization_requires_exact_start_command(
    layout, monkeypatch, unauthorized_content
):
    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["linear"]["delivery_project_id"] = "project-id"
    integrations["discord"].update(
        {
            "enabled": True,
            "guild_id": "123456789012345678",
            "owner_user_id": "42",
            "channels": {"dev_requests": "123456789012345679"},
            "token_set": True,
        }
    )
    client_control.atomic_yaml(config_path, integrations)
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client", issue="FOU-14", title="Exact authorization",
            role="backend-engineer", provider="hermes", repo=repository,
            branch=None, session=None, target="staging",
        ),
    )
    path, record = client_control.load_work(layout, "test-client", work["id"])
    attach_verified_linear_snapshot(layout, "test-client", record, "FOU-14")
    client_control.atomic_yaml(path, record)

    def fake_get(_layout, _slug, endpoint):
        if endpoint.endswith("/channels/123456789012345679"):
            return {"id": "123456789012345679", "guild_id": "123456789012345678"}
        return {
            "id": "999", "channel_id": "123456789012345679",
            "content": unauthorized_content, "author": {"id": "42", "bot": False},
        }

    monkeypatch.setattr(client_control, "discord_client_get", fake_get)

    with pytest.raises(client_control.ClientError, match="exact START command"):
        client_control.authorize_work_start(
            layout,
            Namespace(
                slug="test-client", work_id=work["id"],
                channel_id="123456789012345679", message_id="999",
            ),
        )


def test_work_is_passive_until_context_and_human_authorization_exist(layout):
    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client",
            issue="FOU-143",
            title="Passive backlog candidate",
            role="backend-engineer",
            provider="hermes",
            repo=repository,
            branch=None,
            session=None,
            target="staging",
        ),
    )

    assert work["status"] == "backlog"
    assert work["context"]["complete"] is False
    assert work["authorization"] is None
    with pytest.raises(client_control.ClientError, match="context is incomplete"):
        client_control.transition_work(
            layout, "test-client", work["id"], "todo", actor="pm-agent"
        )
    with pytest.raises(client_control.ClientError, match="only IN_PROGRESS"):
        client_control.start_work_session(layout, "test-client", work["id"])


def test_legacy_work_without_governance_can_be_quarantined_without_forging_authorization(
    layout,
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "in_progress"
    record["context"] = {"complete": False}
    record["authorization"] = None
    client_control.atomic_yaml(path, record)

    with pytest.raises(client_control.ClientError, match="complete Linear context"):
        client_control.transition_work(
            layout, "test-client", work["id"], "agent_review", actor="legacy-agent"
        )

    quarantined = client_control.quarantine_legacy_work(
        layout,
        "test-client",
        work["id"],
        actor="MISSION",
        reason="created by a stale runtime before governed START enforcement",
    )

    assert quarantined["status"] == "blocked"
    assert quarantined["authorization"] is None
    assert quarantined["context"]["complete"] is False
    assert quarantined["legacy_quarantine"]["previous_status"] == "in_progress"
    assert quarantined["legacy_quarantine"]["missing"] == [
        "complete_context",
        "signed_linear_snapshot_receipt",
        "authenticated_start_authorization",
    ]
    assert quarantined["events"][-1]["event"] == "work.legacy_quarantined"

    parsed = client_control.command_parser().parse_args(
        [
            "work",
            "quarantine-legacy",
            "test-client",
            work["id"],
            "--actor",
            "MISSION",
            "--reason",
            "stale runtime",
        ]
    )
    assert parsed.work_command == "quarantine-legacy"


def test_bootstrap_is_safe_with_no_real_client(layout):
    client_control.bootstrap(layout, upgrade=True)

    assert client_control.load_registry(layout)["clients"] == []
    assert "NO DURABLE WORK RECORD / TRACKER ISSUE" in (layout.system / "CLIENT-STANDARD.md").read_text(
        encoding="utf-8"
    )
    assert client_control.show_doctor(layout, None, online=False) == 0


def test_layout_prefers_explicit_agk_control_home_over_virtual_profile_home(
    tmp_path, monkeypatch
):
    virtual_home = tmp_path / "profile" / "home"
    control_home = tmp_path / "mission"
    workspace = control_home / "workspace"
    monkeypatch.setenv("HOME", str(virtual_home))
    monkeypatch.setenv("AGK_CONTROL_HOME", str(control_home))
    monkeypatch.setenv("AGK_CLIENT_WORKSPACE", str(workspace))
    monkeypatch.setenv("AGK_TERMINAL_ROOT", str(ROOT))

    current = client_control.Layout.current()

    assert current.home == control_home.resolve()
    assert current.workspace == workspace.resolve()
    assert current.secrets == (control_home / ".config" / "agk" / "clients").resolve()


def test_bootstrap_upgrade_migrates_an_existing_registry_without_clients(layout):
    layout.system.mkdir(parents=True)
    client_control.atomic_yaml(layout.registry, {"clients": []})

    client_control.bootstrap(layout, upgrade=True)

    assert client_control.yaml_document(layout.registry) == {
        "schema_version": client_control.SCHEMA_VERSION,
        "clients": [],
    }
    assert (layout.system / "AGK_CLIENT_DELIVERY_SYSTEM_MASTER.md").is_file()
    assert "BACKLOG IS PASSIVE" in (
        layout.system / "AGK_CLIENT_DELIVERY_SYSTEM_MASTER.md"
    ).read_text()


def test_bootstrap_upgrade_migrates_existing_client_workflow_and_team(layout):
    client_control.create_client(layout, init_args())
    config = layout.client("test-client") / ".client"
    client_control.atomic_yaml(config / "workflow.yaml", {"schema_version": 1, "legacy": True})
    client_control.atomic_yaml(config / "team.yaml", {"schema_version": 1, "client_id": "test-client"})

    client_control.bootstrap(layout, upgrade=True)

    workflow = client_control.yaml_document(config / "workflow.yaml")
    team = client_control.yaml_document(config / "team.yaml")
    assert workflow["schema_version"] == 5
    assert workflow["invariants"]["explicit_human_start_authorization_required"] is True
    assert workflow["autonomy"]["default_behavior"] == "decide-act-verify-record-continue"
    assert team["schema_version"] == 3
    assert team["client_id"] == "test-client"
    assert team["hermes_profile"] == client_control.hermes_profile_id("test-client")
    operations = client_control.yaml_document(config / "operations.yaml")
    assert operations["contract"] == "agk-client-operations/v1"
    backups = layout.system / "audit" / "client-config-migrations" / "test-client"
    assert (backups / "workflow.schema-1.yaml").is_file()
    assert (backups / "team.schema-1.yaml").is_file()


def test_bootstrap_upgrade_preserves_client_governance_customizations(layout):
    client_control.create_client(layout, init_args())
    config = layout.client("test-client") / ".client"
    client_control.atomic_yaml(
        config / "workflow.yaml",
        {
            "schema_version": 1,
            "custom_governance": {"change_window": "client-approved-only"},
            "intake": {"product_definition_requires": ["client_specific_evidence"]},
        },
    )
    client_control.atomic_yaml(
        config / "team.yaml",
        {
            "schema_version": 1,
            "client_id": "test-client",
            "roles": {
                "client-specialist": {
                    "description": "Client-specific retained role",
                    "allowed_channels": ["client-private"],
                }
            },
        },
    )

    client_control.bootstrap(layout, upgrade=True)

    workflow = client_control.yaml_document(config / "workflow.yaml")
    team = client_control.yaml_document(config / "team.yaml")
    assert workflow["custom_governance"] == {
        "change_window": "client-approved-only"
    }
    assert "client_specific_evidence" in workflow["intake"][
        "product_definition_requires"
    ]
    assert "full_issue_description" in workflow["intake"][
        "product_definition_requires"
    ]
    assert team["roles"]["client-specialist"]["description"] == (
        "Client-specific retained role"
    )
    assert "project-manager" in team["roles"]


def test_client_upgrade_rejects_incompatible_governance_types():
    with pytest.raises(client_control.ClientError, match="incompatible type"):
        client_control.merge_client_upgrade(
            {"invariants": {"production_disabled": True}},
            {"invariants": "disabled"},
        )


def test_client_upgrade_rejects_scalar_default_replaced_by_container():
    with pytest.raises(client_control.ClientError, match="incompatible type"):
        client_control.merge_client_upgrade(
            {"flag": False},
            {"flag": {"nested": False}},
        )


@pytest.mark.parametrize(
    ("default", "current"),
    [
        (True, 1),
        (True, "true"),
        (4, "4"),
        (1.5, 1),
        (True, None),
    ],
)
def test_client_upgrade_rejects_incompatible_scalar_types(default, current):
    with pytest.raises(client_control.ClientError, match="incompatible type"):
        client_control.merge_client_upgrade(
            {"value": default},
            {"value": current},
        )


def test_client_upgrade_allows_configured_scalar_for_null_placeholder():
    assert client_control.merge_client_upgrade(
        {"external_id": None},
        {"external_id": "configured-id"},
    ) == {"external_id": "configured-id"}


def test_dry_run_makes_no_files_or_external_calls(layout, monkeypatch):
    monkeypatch.setattr(
        client_control.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("dry-run attempted an external process"),
    )

    result = client_control.create_client(layout, init_args("dry-client", dry_run=True))

    assert result["dry_run"] is True
    assert result["external_actions"] == []
    assert not layout.workspace.exists()


def test_client_init_is_transactional_private_and_registered(layout):
    result = client_control.create_client(layout, init_args())
    root = layout.client("test-client")

    assert result["external_actions"] == []
    assert root.is_dir()
    assert (root.stat().st_mode & 0o077) == 0
    assert (layout.secret_file("test-client").stat().st_mode & 0o777) == 0o600
    assert f"export AGK_CLIENT_WORKSPACE={layout.workspace}" in layout.secret_file(
        "test-client"
    ).read_text()
    assert client_control.load_registry(layout)["clients"][0]["id"] == "test-client"
    assert (root / ".client" / "workflow.yaml").is_file()
    runtime = client_control.yaml_document(root / ".client" / "runtime.yaml")
    assert runtime["browser_qa"]["authenticated_session_required"] is True
    assert runtime["browser_qa"]["enabled"] is False
    assert runtime["browser_qa"]["profiles"] == []
    assert [item["id"] for item in runtime["browser_qa"]["viewports"]] == [
        "mobile", "ipad", "desktop", "large_desktop"
    ]
    assert runtime["browser_qa"]["capture_policy"] == (
        "full_page_unobstructed_after_dismissing_overlays"
    )
    assert (root / ".client" / "team.yaml").is_file()
    assert client_control.show_doctor(layout, "test-client", online=False) == 0

    with pytest.raises(client_control.ClientError, match="already exists"):
        client_control.create_client(layout, init_args())


def test_new_clients_include_dev_intake_and_harness_engineering_loop(layout):
    client_control.create_client(layout, init_args())
    root = layout.client("test-client")
    workflow = client_control.yaml_document(root / ".client" / "workflow.yaml")
    team = client_control.yaml_document(root / ".client" / "team.yaml")
    integrations = client_control.yaml_document(root / ".client" / "integrations.yaml")

    assert "dev_requests" in integrations["discord"]["channels"]
    assert team["discord_channels"]["dev_requests"] == "dev-requests"
    assert team["execution_model"]["supervision_surface"] == "agk_tui"
    assert team["agent_collaboration"]["changes_requested_resumes_same_session"] is True
    assert workflow["display_names"]["automated_qa"] == "QA"
    assert workflow["display_names"]["ready_for_cto"] == "CTO Review"
    assert workflow["display_names"]["security_review"] == "Security Review"
    assert workflow["display_names"]["business_review"] == "Business Review"
    assert workflow["invariants"]["real_navigation_required"] is True
    assert workflow["invariants"]["backlog_is_passive"] is True
    assert workflow["invariants"]["agents_never_mark_done"] is True
    assert workflow["harness_engineering_loop"]["qa"]["browser"] == (
        "exact_authenticated_client_profile_from_runtime"
    )
    assert workflow["harness_engineering_loop"]["qa"]["authentication_reprobe_after_restart"] is True
    assert workflow["gates"]["ready_for_cto"]["validation_request_channel"] == "cto_inbox"
    assert workflow["gates"]["done"]["agents_forbidden_from_provider_state_mutation"] is True
    assert workflow["linear_evidence_policy"]["comment_every_material_gate"] is True
    assert workflow["linear_evidence_policy"]["attach_all_required_viewports"] is True
    assert workflow["linear_evidence_policy"]["preserve_failed_attempts_and_corrections"] is True
    assert workflow["harness_engineering_loop"]["correction_loop"]["on_failure"] == "return_to_in_progress"
    assert "hermes_session" in workflow["harness_engineering_loop"]["correction_loop"]["preserve"]


def test_client_team_uses_dedicated_project_manager_orchestration(layout):
    client_control.create_client(layout, init_args())

    team = client_control.yaml_document(
        layout.client("test-client") / ".client" / "team.yaml"
    )

    assert team["orchestrator"] == {
        "role": "atlas",
        "provider": "hermes",
        "public_alias": "project-manager",
    }
    assert set(team["canonical_identities"]) == {
        "atlas", "architect", "forge", "sentinel", "release-engineer", "sre",
    }
    assert team["role_aliases"]["project-manager"] == "atlas"
    assert team["role_aliases"]["frontend-engineer"] == "forge"
    assert team["roles"]["project-manager"]["scope"] == "delivery-orchestration"
    assert team["roles"]["product-manager"]["scope"] == "product-direction"
    assert team["roles"]["product-manager"]["reports_to"] == "project-manager"
    assert team["execution_model"] == {
        "client_profile": "dedicated",
        "agents": "on_demand_preserved_sessions",
        "discord_identity": "dedicated_devops_atlas_bot",
        "production_gate": "cto_required",
        "supervision_surface": "agk_tui",
        "specialist_sessions": "preserved_and_visible",
    }
    assert team["human_gates"]["issue_human_only_fields"] == [
        "human_decision",
        "human_approval",
        "production_authorization",
    ]


def test_doctor_rejects_regressed_delivery_harness(layout):
    client_control.create_client(layout, init_args())
    root = layout.client("test-client")
    workflow_path = root / ".client" / "workflow.yaml"
    workflow = client_control.yaml_document(workflow_path)
    workflow["invariants"]["backlog_is_passive"] = False
    workflow["invariants"]["real_navigation_required"] = False
    workflow["display_names"].pop("security_review")
    workflow["intake"]["product_definition_requires"].remove("source")
    workflow["gates"]["business_review"]["human_decision_required"] = False
    workflow["gates"]["ready_for_cto"]["requires"].remove(
        "security_passed_or_not_required"
    )
    client_control.atomic_yaml(workflow_path, workflow)
    team_path = root / ".client" / "team.yaml"
    team = client_control.yaml_document(team_path)
    team["discord_channels"].pop("dev_requests")
    team["execution_model"].pop("supervision_surface")
    team["agent_collaboration"]["changes_requested_resumes_same_session"] = False
    client_control.atomic_yaml(team_path, team)

    failures = [
        message
        for level, message in client_control.doctor_one(
            layout, "test-client", online=False
        )
        if level == "fail"
    ]

    assert "workflow invariant backlog_is_passive" in failures
    assert "workflow invariant real_navigation_required" in failures
    assert "workflow maps Security Review" in failures
    assert "Linear product definition contract is complete" in failures
    assert "Business Review is an actor-attributed human decision" in failures
    assert "CTO Review accepts a recorded security disposition" in failures
    assert "team has a dedicated dev-requests intake channel" in failures
    assert "team sessions are supervised in AGK TUI" in failures
    assert "changes requested preserves the same agent session" in failures


def test_doctor_rejects_regressed_team_orchestration(layout):
    client_control.create_client(layout, init_args())
    path = layout.client("test-client") / ".client" / "team.yaml"
    team = client_control.yaml_document(path)
    team["orchestrator"]["role"] = "platform-lead"
    team["execution_model"]["discord_identity"] = "shared_mission_bot_with_role_labels"
    client_control.atomic_yaml(path, team)

    checks = client_control.doctor_one(layout, "test-client", online=False)

    failures = [message for level, message in checks if level == "fail"]
    assert "team Atlas is the Hermes DevOps orchestrator" in failures
    assert "team uses a dedicated DevOps Atlas Discord bot" in failures


def test_client_init_declares_vercel_convex_and_drive_as_first_class_integrations(layout):
    client_control.create_client(
        layout,
        init_args(vercel=True, convex=True, google_drive=True),
    )

    integrations = client_control.yaml_document(
        layout.client("test-client") / ".client" / "integrations.yaml"
    )

    assert integrations["vercel"] == {
        "enabled": True,
        "account_alias": "client-test-client-vercel",
        "team_id": None,
        "project_ids": [],
    }
    assert integrations["convex"] == {
        "enabled": True,
        "credential_backend": "client-secret-store",
        "deployment_ids": {"development": None, "staging": None, "production": None},
        "token_set": False,
    }
    assert integrations["google_drive"] == {
        "enabled": True,
        "account_alias": "client-test-client-googledrive",
        "account_selector": None,
        "meeting_summary_folder_ids": [],
        "shared_drive_id": None,
        "supports_all_drives": True,
        "processed_state": "state/meeting-intake/processed.json",
        "intake_policy": {
            "destination": "linear",
            "apply_mode": "candidate_backlog_only",
            "dedupe_key": "drive_file_id+content_hash",
            "agent_statuses": ["backlog"],
            "human_start_status": "todo",
            "human_review_states": ["business_review", "ready_for_cto"],
            "human_only_decisions": [
                "business_review_result", "approved_for_prod", "done",
            ],
            "human_only_statuses": ["cto_approved", "done"],
            "system_only_statuses": ["ready_to_deploy", "production", "verified"],
            "human_gate_mode": "proposal_only",
        },
    }
    team = client_control.yaml_document(
        layout.client("test-client") / ".client" / "team.yaml"
    )
    assert team["roles"]["meeting-intake-coordinator"]["scope"] == "drive-to-linear"
    plan = client_control.integration_plan(layout, "test-client")
    aliases = {item["account_alias"] for item in plan["connections"]}
    assert "client-test-client-vercel" in aliases
    assert "client-test-client-googledrive" in aliases
    assert "client-test-client-convex" not in aliases


def test_convex_online_checks_require_token_and_every_environment():
    config = {
        "enabled": True,
        "token_set": False,
        "deployment_ids": {"development": None, "staging": None, "production": None},
    }

    assert client_control.convex_checks(config) == [
        ("fail", "Convex client credential is not configured"),
        ("fail", "Convex deployment id is missing: development"),
        ("fail", "Convex deployment id is missing: staging"),
        ("fail", "Convex deployment id is missing: production"),
    ]

    config["token_set"] = True
    config["deployment_ids"] = {
        "development": "dev:dentistry",
        "staging": "staging:dentistry",
        "production": "prod:dentistry",
    }
    assert client_control.convex_checks(config) == [
        ("ok", "Convex client credential is configured"),
        ("ok", "Convex deployment ids are explicit for development, staging and production"),
    ]


def test_composio_executable_uses_canonical_agk_fallback(monkeypatch):
    canonical = Path("/usr/local/lib/agk-terminal/bin/composio")
    monkeypatch.setattr(client_control.shutil, "which", lambda _name: None)
    monkeypatch.setattr(Path, "is_file", lambda self: self == canonical)

    assert client_control.composio_executable() == canonical


def test_composio_checks_accept_local_vault_discord_bot(monkeypatch):
    monkeypatch.setattr(client_control, "composio_connections", lambda: {})
    integrations = {
        "discord": {
            "enabled": True,
            "provisioning_backend": "client-discord-bot",
            "token_set": True,
            "bot_id": "1542493917541437480",
        }
    }

    assert client_control.composio_checks(integrations) == [
        ("ok", "Discord dedicated bot credential is configured in the client vault")
    ]


def test_composio_checks_use_explicit_account_selector_when_alias_is_not_preserved(monkeypatch):
    monkeypatch.setattr(
        client_control,
        "composio_connections",
        lambda: {
            "googledrive": [
                {"word_id": "googledrive_kohl-scent", "status": "ACTIVE"}
            ]
        },
    )
    integrations = {
        "google_drive": {
            "enabled": True,
            "account_alias": "client-test-client-googledrive",
            "account_selector": "googledrive_kohl-scent",
        }
    }

    assert client_control.composio_checks(integrations) == [
        ("ok", "Composio google_drive account is active: googledrive_kohl-scent")
    ]


def test_integration_plan_requires_client_scoped_composio_aliases(layout):
    client_control.create_client(layout, init_args())

    plan = client_control.integration_plan(layout, "test-client")

    aliases = {item["account_alias"] for item in plan["connections"]}
    assert aliases == {
        "client-test-client-linear",
        "client-test-client-github",
        "client-test-client-discordbot",
    }
    assert all("--alias" in item["command"] for item in plan["connections"])
    assert all("--no-wait" in item["command"] for item in plan["connections"])
    assert plan["external_writes"] is False


def test_no_linear_issue_or_unregistered_repository_means_no_work(layout):
    client_control.create_client(layout, init_args())
    args = Namespace(
        slug="test-client",
        issue="not-an-issue",
        title="Unsafe work",
        role="backend-engineer",
        provider="hermes",
        repo="test-org/product",
        branch=None,
        session=None,
        target="development",
    )

    with pytest.raises(client_control.ClientError, match="Linear issue"):
        client_control.create_work(layout, args)

    args.issue = "FOU-142"
    with pytest.raises(client_control.ClientError, match="not declared"):
        client_control.create_work(layout, args)
    assert not list((layout.client("test-client") / "state" / "work").iterdir())


def test_request_changes_preserves_the_exact_execution_context(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    path, record = client_control.load_work(layout, "test-client", work["id"])
    original = {
        "session": record["agent"]["session"],
        "repo": record["repository"]["repo"],
        "branch": record["repository"]["branch"],
        "issue": record["linear"]["issue"],
    }
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(path, record)

    resumed = client_control.request_changes(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            feedback="Handle corrupted PDF files and expose retry.",
            actor="cto-user",
        ),
    )

    assert resumed["status"] == "in_progress"
    assert resumed["agent"]["session"] == original["session"]
    assert resumed["repository"]["repo"] == original["repo"]
    assert resumed["repository"]["branch"] == original["branch"]
    assert resumed["linear"]["issue"] == original["issue"]
    assert resumed["events"][-1]["resumed_context"]["session"] == original["session"]


def test_image_evidence_must_decode(layout):
    client_control.create_client(layout, init_args())
    fake = layout.client("test-client") / "artifacts" / "fake.png"
    fake.write_bytes(b"not-an-image")

    with pytest.raises(client_control.ClientError, match="does not decode"):
        client_control.client_evidence_artifact(
            layout, "test-client", str(fake), suffixes={".png"}
        )


def test_browser_url_matching_rejects_host_prefix_attack():
    assert client_control.canonical_browser_url("https://staging.test") != (
        client_control.canonical_browser_url("https://staging.test.evil/path")
    )


def test_qa_evidence_rejects_a_single_valid_screenshot(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    screenshot = layout.client("test-client") / "artifacts" / "mobile.png"
    from PIL import Image

    Image.new("RGB", (390, 844), color="white").save(screenshot)
    artifact = client_control.client_evidence_artifact(
        layout,
        "test-client",
        str(screenshot),
        suffixes={".png"},
    )
    artifact["viewport"] = "mobile"

    with pytest.raises(client_control.ClientError, match="missing required viewport"):
        client_control.validate_qa_evidence(
            layout,
            "test-client",
            work["id"],
            {"screenshots": [artifact]},
        )


def test_qa_evidence_rejects_forged_stored_viewport_dimensions(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    screenshot = layout.client("test-client") / "artifacts" / "one-pixel.png"
    from PIL import Image

    Image.new("RGB", (1, 1), color="white").save(screenshot)
    decoded = client_control.client_evidence_artifact(
        layout,
        "test-client",
        str(screenshot),
        suffixes={".png"},
    )
    runtime = client_control.yaml_document(
        layout.client("test-client") / ".client" / "runtime.yaml"
    )
    screenshots = []
    for viewport in runtime["browser_qa"]["viewports"]:
        forged = dict(decoded)
        forged.update(
            {
                "viewport": viewport["id"],
                "width": viewport["width"],
                "height": viewport["height"],
            }
        )
        screenshots.append(forged)

    with pytest.raises(client_control.ClientError, match="decoded dimensions"):
        client_control.validate_qa_evidence(
            layout,
            "test-client",
            work["id"],
            {"screenshots": screenshots},
        )


def test_qa_evidence_rejects_reduced_runtime_viewport_policy(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    runtime_path = layout.client("test-client") / ".client" / "runtime.yaml"
    runtime = client_control.yaml_document(runtime_path)
    runtime["browser_qa"]["viewports"] = [
        {"id": "mobile", "width": 390, "height": 844}
    ]
    client_control.atomic_yaml(runtime_path, runtime)
    screenshot = layout.client("test-client") / "artifacts" / "mobile.png"
    from PIL import Image

    Image.new("RGB", (390, 844), color="white").save(screenshot)
    artifact = client_control.client_evidence_artifact(
        layout,
        "test-client",
        str(screenshot),
        suffixes={".png"},
    )
    artifact.update({"viewport": "mobile", "width": 390, "height": 844})

    with pytest.raises(client_control.ClientError, match="canonical four viewports"):
        client_control.validate_qa_evidence(
            layout,
            "test-client",
            work["id"],
            {"screenshots": [artifact]},
        )


def test_browser_session_rejects_navigation_without_authenticated_binding(layout):
    import sqlite3

    client_control.create_client(layout, init_args())
    profile = client_control.yaml_document(
        layout.client("test-client") / ".client" / "manifest.yaml"
    )["profile"]["hermes_profile"]
    profile_home = layout.home / ".hermes" / "profiles" / profile
    profile_home.mkdir(parents=True)
    db = sqlite3.connect(profile_home / "state.db")
    db.execute(
        "create table sessions(id text primary key, source text, started_at real, last_activity_at real)"
    )
    db.execute(
        "create table messages(session_id text, role text, tool_name text, content text, timestamp real)"
    )
    db.execute(
        "insert into sessions values(?,?,?,?)",
        ("qa-session-unbound", "kanban", 1000.0, 1100.0),
    )
    db.execute(
        "insert into messages values(?,?,?,?,?)",
        (
            "qa-session-unbound",
            "tool",
            "browser_exec",
            json.dumps(
                {
                    "url": "https://staging.test",
                    "page_title": "Test",
                    "browser_profile_id": "test-staging-user",
                    "authenticated_principal": "test-user",
                    "authentication_probe_sha256": "a" * 64,
                }
            ),
            1050.0,
        ),
    )
    db.commit()
    db.close()

    with pytest.raises(client_control.ClientError, match="tool call binding"):
        client_control.verify_browser_session(
            layout,
            "test-client",
            "qa-session-unbound",
            url="https://staging.test",
            started_at=1000.0,
            finished_at=1100.0,
            profile_binding={
                "browser_profile_id": "test-staging-user",
                "authenticated_principal": "test-user",
                "authentication_probe_sha256": "a" * 64,
            },
        )


def test_browser_profile_binding_is_exact_and_case_sensitive():
    assert not client_control.browser_payload_has_profile_binding(
        {
            "browser_profile_id": "Test-Staging-User",
            "authenticated_principal": "Test-User",
            "authentication_probe_sha256": "A" * 64,
        },
        {
            "browser_profile_id": "test-staging-user",
            "authenticated_principal": "test-user",
            "authentication_probe_sha256": "a" * 64,
        },
    )


def test_browser_navigation_rejects_disjoint_nested_authentication_binding():
    binding = {
        "browser_profile_id": "test-staging-user",
        "authenticated_principal": "test-user",
        "authentication_probe_sha256": "a" * 64,
    }
    payload = {
        "navigation": {"url": "https://staging.test"},
        "unrelated_page_data": binding,
    }

    assert not client_control.browser_payload_has_bound_navigation(
        payload,
        client_control.canonical_browser_url("https://staging.test"),
        binding,
    )


def test_browser_profile_binding_rejects_unconfigured_authenticated_principal(layout):
    client_control.create_client(layout, init_args())
    runtime_path = layout.client("test-client") / ".client" / "runtime.yaml"
    runtime = client_control.yaml_document(runtime_path)
    runtime["browser_qa"].update(
        {
            "enabled": True,
            "profiles": [
                {
                    "id": "staging-user",
                    "environment": "staging",
                    "role": "user",
                    "authenticated_verified": True,
                }
            ],
        }
    )
    client_control.atomic_yaml(runtime_path, runtime)

    with pytest.raises(client_control.ClientError, match="authentication is unverified"):
        client_control.validate_browser_qa_profile(
            layout,
            "test-client",
            {
                "browser_profile_id": "staging-user",
                "environment": "staging",
                "role": "user",
                "authenticated_principal": "attacker@example.test",
                "authentication_probe_sha256": "b" * 64,
            },
        )


def test_qa_pass_requires_real_artifacts_and_browser_session_provenance(layout):
    import sqlite3

    client_control.create_client(layout, init_args())
    work = make_work(layout)
    runtime_path = layout.client("test-client") / ".client" / "runtime.yaml"
    runtime = client_control.yaml_document(runtime_path)
    runtime["browser_qa"].update(
        {
            "enabled": True,
            "profiles": [
                {
                    "id": "test-staging-user",
                    "environment": "staging",
                    "role": "standard-user",
                    "authenticated_verified": True,
                    "authenticated_principal": "test-user",
                    "authentication_probe_sha256": "a" * 64,
                }
            ],
        }
    )
    client_control.atomic_yaml(runtime_path, runtime)
    profile = client_control.yaml_document(
        layout.client("test-client") / ".client" / "manifest.yaml"
    )["profile"]["hermes_profile"]
    profile_home = layout.home / ".hermes" / "profiles" / profile
    profile_home.mkdir(parents=True)
    db = sqlite3.connect(profile_home / "state.db")
    db.execute("create table sessions(id text primary key, source text, started_at real, last_activity_at real)")
    db.execute(
        "create table messages(session_id text, role text, tool_name text, content text, "
        "timestamp real, tool_call_id text, tool_calls text)"
    )
    db.execute("insert into sessions values(?,?,?,?)", ("qa-session-1", "kanban", 1000.0, 1100.0))
    db.execute(
        "insert into messages values(?,?,?,?,?,?,?)",
        (
            "qa-session-1",
            "assistant",
            None,
            "",
            1040.0,
            None,
            json.dumps(
                [
                    {
                        "id": "browser-call-1",
                        "function": {
                            "name": "browser_exec",
                            "arguments": json.dumps(
                                {
                                    "code": "trusted browser navigation probe",
                                    "session": "test-staging-user",
                                }
                            ),
                        },
                    }
                ]
            ),
        ),
    )
    db.execute(
        "insert into messages values(?,?,?,?,?,?,?)",
        (
            "qa-session-1",
            "tool",
            "browser_exec",
            (
                '<untrusted_tool_result source="browser_exec">\n'
                "External content follows.\n"
                + json.dumps(
                    {
                        "url": "https://staging.test",
                        "page_title": "Test",
                        "browser_profile_id": "test-staging-user",
                        "authenticated_principal": "test-user",
                        "authentication_probe_sha256": "a" * 64,
                    }
                )
                + "\n</untrusted_tool_result>"
            ),
            1050.0,
            "browser-call-1",
            None,
        ),
    )
    db.commit()
    db.close()
    from PIL import Image
    screenshot_paths = []
    for viewport in runtime["browser_qa"]["viewports"]:
        screenshot = (
            layout.client("test-client")
            / "artifacts"
            / f"qa-{viewport['id']}.png"
        )
        Image.new(
            "RGB",
            (viewport["width"], viewport["height"]),
            color="white",
        ).save(screenshot)
        screenshot_paths.append(str(screenshot))
    report = layout.client("test-client") / "artifacts" / "browser-report.json"
    report.write_text(
        json.dumps(
            {
                "session_id": "qa-session-1",
                "work_id": work["id"],
                "actor": "qa-agent",
                "started_at": 1000.0,
                "finished_at": 1100.0,
                "real_browser_navigation_succeeded": True,
                "url": "https://staging.test",
                "page_title": "Test",
                "browser_profile_id": "test-staging-user",
                "environment": "staging",
                "role": "standard-user",
                "authenticated_principal": "test-user",
                "authentication_probe_sha256": "a" * 64,
            }
        )
    )

    updated = client_control.update_evidence(
        layout,
        Namespace(
            slug="test-client", work_id=work["id"], actor="qa-agent",
            pull_request=None, commit=None, engineering_review=None, ci=None,
            qa="passed", security=None, security_decision_id=None,
            preview=None, staging_build=None, screenshot=screenshot_paths,
            validation_step=["Navigate the real user flow and verify the result"],
            browser_report=str(report), qa_session_id="qa-session-1",
            rollback_plan=None, risk=None, production_health=None,
            linear_done=False,
        ),
    )

    assert updated["evidence"]["qa_passed"] is True
    assert {
        item["viewport"] for item in updated["evidence"]["screenshots"]
    } == {"mobile", "ipad", "desktop", "large_desktop"}
    assert all(len(item["sha256"]) == 64 for item in updated["evidence"]["screenshots"])
    assert updated["evidence"]["qa_browser_provenance"]["session_id"] == "qa-session-1"


def test_intermediate_delivery_gates_fail_closed(layout, monkeypatch):
    monkeypatch.setattr(client_control, "validate_qa_evidence", lambda *_args: None)
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_id = work["id"]
    client_control.transition_work(
        layout, "test-client", work_id, "agent_review", actor="engineer"
    )
    with pytest.raises(client_control.ClientError, match="engineering review"):
        client_control.transition_work(
            layout, "test-client", work_id, "automated_qa", actor="reviewer"
        )
    path, record = client_control.load_work(layout, "test-client", work_id)
    record["evidence"]["engineering_review_passed"] = True
    client_control.atomic_yaml(path, record)
    client_control.transition_work(
        layout, "test-client", work_id, "automated_qa", actor="reviewer"
    )
    with pytest.raises(client_control.ClientError, match="QA evidence"):
        client_control.transition_work(
            layout, "test-client", work_id, "security_review", actor="qa"
        )
    path, record = client_control.load_work(layout, "test-client", work_id)
    record["evidence"].update(
        {
            "qa_passed": True,
            "screenshots": ["evidence/before-after.png"],
            "validation_steps": ["Navigate real flow and verify expected state"],
        }
    )
    client_control.atomic_yaml(path, record)
    client_control.transition_work(
        layout, "test-client", work_id, "security_review", actor="qa"
    )
    with pytest.raises(client_control.ClientError, match="security disposition"):
        client_control.transition_work(
            layout, "test-client", work_id, "staging", actor="security"
        )
    path, record = client_control.load_work(layout, "test-client", work_id)
    record["repository"].update(
        {"pull_request": "https://github.test/pr/1", "commit": "abc123"}
    )
    record["evidence"].update(
        {
            "ci_passed": True,
            "security_disposition": "not_required",
            "security_decision_id": "SEC-NA-1",
            "rollback_plan": "Revert PR",
        }
    )
    client_control.atomic_yaml(path, record)
    client_control.transition_work(
        layout, "test-client", work_id, "staging", actor="security"
    )
    with pytest.raises(client_control.ClientError, match="staging evidence"):
        client_control.transition_work(
            layout, "test-client", work_id, "business_review", actor="release"
        )
    path, record = client_control.load_work(layout, "test-client", work_id)
    record["evidence"].update(
        {
            "staging_preview": "https://staging.test",
            "staging_build_version": "preview-1",
        }
    )
    client_control.atomic_yaml(path, record)
    client_control.transition_work(
        layout, "test-client", work_id, "business_review", actor="release"
    )
    with pytest.raises(client_control.ClientError, match="Business Review"):
        client_control.transition_work(
            layout, "test-client", work_id, "ready_for_cto", actor="pm"
        )


def test_delivery_gates_and_release_controller_fail_closed(layout, monkeypatch):
    monkeypatch.setattr(client_control, "validate_qa_evidence", lambda *_args: None)
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_id = work["id"]
    path, record = client_control.load_work(layout, "test-client", work_id)
    record["repository"].update(
        {
            "pull_request": "https://github.test/pr/284",
            "commit": "882ba43",
        }
    )
    record["evidence"].update(
        {
            "engineering_review_passed": True,
            "ci_passed": True,
            "qa_passed": True,
            "security_disposition": "passed",
            "security_decision_id": "SEC-1",
            "staging_preview": "https://staging.test/FOU-142",
            "staging_build_version": "preview-284",
            "screenshots": ["evidence/qa.png"],
            "validation_steps": ["Navigate the real flow"],
            "business_review": {
                "result": "approved",
                "actor_id": "product-owner",
                "decision_id": "BUS-1",
                "at": "2026-08-27T00:00:00+00:00",
            },
            "rollback_plan": "Revert PR 284",
            "risk": "low",
        }
    )
    client_control.atomic_yaml(path, record)
    for target in (
        "agent_review",
        "automated_qa",
        "security_review",
        "staging",
        "business_review",
        "ready_for_cto",
    ):
        client_control.transition_work(
            layout, "test-client", work_id, target, actor="delivery-system"
        )

    with pytest.raises(client_control.ClientError, match="release controller is disabled"):
        client_control.approve_work(
            layout,
            Namespace(
                slug="test-client",
                work_id=work_id,
                approval_id="UNTRUSTED",
                actor="untrusted-cli",
            ),
        )
    with pytest.raises(client_control.ClientError, match="forbidden"):
        client_control.start_run(
            layout,
            Namespace(
                slug="test-client",
                work_id=work_id,
                action="delete_database",
                actor="any-agent",
                machine="test-prod-01",
                commit="882ba43",
                before=None,
                after=None,
                approval_id="UNTRUSTED",
                rollback_available=False,
            ),
        )
    with pytest.raises(client_control.ClientError, match="authoritative"):
        client_control.update_evidence(
            layout,
            Namespace(
                slug="test-client",
                work_id=work_id,
                actor="untrusted-cli",
                pull_request=None,
                commit=None,
                ci=None,
                qa=None,
                security=None,
                preview=None,
                risk=None,
                production_health=None,
                linear_done=True,
            ),
        )


def test_review_card_only_exposes_the_valid_human_action(layout):
    client_control.create_client(layout, init_args())
    record = make_work(layout)
    record["status"] = "ready_for_cto"

    labels = {
        button["label"]
        for button in client_control.review_card(
            record, release_controller_enabled=True
        )["buttons"]
    }
    assert "APPROVE" in labels
    assert "DEPLOY" not in labels

    record["status"] = "ready_to_deploy"
    labels = {
        button["label"]
        for button in client_control.review_card(
            record, release_controller_enabled=True
        )["buttons"]
    }
    assert "DEPLOY" in labels
    assert "APPROVE" not in labels


def test_linear_webhook_uses_raw_body_hmac_and_replay_window():
    secret = "test-signing-secret"
    now_ms = 1_787_745_600_000
    body = json.dumps(
        {"type": "Issue", "action": "update", "webhookTimestamp": now_ms},
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    verified = client_control.verify_linear_webhook(
        body, signature, secret, now_ms=now_ms
    )
    assert verified["type"] == "Issue"

    with pytest.raises(client_control.ClientError, match="signature"):
        client_control.verify_linear_webhook(
            body + b" ", signature, secret, now_ms=now_ms
        )
    with pytest.raises(client_control.ClientError, match="replay window"):
        client_control.verify_linear_webhook(
            body, signature, secret, now_ms=now_ms + 61_000
        )


def test_discord_plan_has_no_write_and_apply_is_idempotent_in_contract(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    plan = client_control.discord_plan(layout, "test-client")
    assert plan["external_writes"] is True
    assert plan["idempotent"] is True
    assert plan["rollback_on_failure"] is True

    remote = []
    counter = iter(range(100, 200))

    def fake_proxy(method, url, account, data=None):
        assert account == "client-test-client-discordbot"
        if method == "GET":
            return list(remote)
        if method == "POST":
            value = {"id": str(next(counter)), **data}
            remote.append(value)
            return value
        if method == "DELETE":
            channel_id = url.rsplit("/", 1)[-1]
            remote[:] = [item for item in remote if item["id"] != channel_id]
            return {}
        raise AssertionError(method)

    monkeypatch.setattr(client_control, "composio_proxy", fake_proxy)
    first = client_control.discord_apply(
        layout, Namespace(slug="test-client", yes=True)
    )
    second = client_control.discord_apply(
        layout, Namespace(slug="test-client", yes=True)
    )

    assert len(first["created_resource_ids"]) == 8
    assert second["created_resource_ids"] == []
    assert len(remote) == 8


def test_discord_apply_rolls_back_remote_resources_when_local_commit_fails(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    remote = []
    deleted = []
    counter = iter(range(200, 300))

    def fake_proxy(method, url, account, data=None):
        assert account == "client-test-client-discordbot"
        if method == "GET":
            return list(remote)
        if method == "POST":
            value = {"id": str(next(counter)), **data}
            remote.append(value)
            return value
        if method == "DELETE":
            channel_id = url.rsplit("/", 1)[-1]
            deleted.append(channel_id)
            remote[:] = [item for item in remote if item["id"] != channel_id]
            return {}
        raise AssertionError(method)

    original_atomic_yaml = client_control.atomic_yaml

    def fail_integration_commit(path, value, mode=0o600):
        if path.name == "integrations.yaml":
            raise OSError("simulated local commit failure")
        return original_atomic_yaml(path, value, mode)

    monkeypatch.setattr(client_control, "composio_proxy", fake_proxy)
    monkeypatch.setattr(client_control, "atomic_yaml", fail_integration_commit)

    with pytest.raises(client_control.ClientError, match="rolled back"):
        client_control.discord_apply(layout, Namespace(slug="test-client", yes=True))

    assert remote == []
    assert len(deleted) == 8


def test_agent_session_start_is_bound_and_cannot_bypass_review_state(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, work = client_control.load_work(layout, "test-client", work["id"])
    manifest = client_control.client_configs(layout, "test-client")["manifest.yaml"]
    profile = manifest["profile"]["hermes_profile"]
    profile_home = layout.home / ".hermes" / "profiles" / profile
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text("model: test\n", encoding="utf-8")

    class FakeRuntime:
        def __init__(self):
            self.sent = []

        def has_session(self, _session):
            return True

        def send_input(self, session, prompt):
            self.sent.append((session, prompt))

    class FakeRegistry:
        def __init__(self):
            self.runtime = FakeRuntime()
            self.records = {}
            self.created_command = None

        def get(self, name):
            return self.records.get(name)

        def create(self, *, name, command, client, mission, **_kwargs):
            self.created_command = command
            record = {
                "id": "runtime-1",
                "name": name,
                "client": client,
                "mission": mission,
                "rmux_session": "rmux-runtime-1",
            }
            self.records[name] = record
            return record

    registry = FakeRegistry()
    monkeypatch.setattr(
        client_control, "agk_runtime", lambda _layout: (object(), registry)
    )
    started = client_control.start_work_session(layout, "test-client", work["id"])

    assert started["created"] is True
    assert registry.created_command[1:3] == ["-p", profile]
    assert work["id"] in registry.runtime.sent[0][1]
    assert "FOU-142" in registry.runtime.sent[0][1]

    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    with pytest.raises(client_control.ClientError, match="IN_PROGRESS"):
        client_control.start_work_session(layout, "test-client", work["id"])


def test_client_activation_creates_a_blank_isolated_hermes_profile(layout, monkeypatch):
    client_control.create_client(layout, init_args())
    manifest = client_control.client_configs(layout, "test-client")["manifest.yaml"]
    profile = manifest["profile"]["hermes_profile"]
    profile_home = layout.home / ".hermes" / "profiles" / profile
    commands = []
    monkeypatch.setattr(client_control.shutil, "which", lambda name: "/bin/hermes")

    def fake_run(command, **_kwargs):
        commands.append(command)
        profile_home.mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(client_control.subprocess, "run", fake_run)
    result = client_control.activate_client(
        layout, Namespace(slug="test-client", yes=True)
    )

    assert result["created"] is True
    assert result["setup_required"] is True
    assert result["next_command"] == f"hermes --profile {profile} setup"
    assert "--no-alias" in commands[0]
    assert "--clone" not in commands[0]
    assert (profile_home / "SOUL.md").is_file()
    assert (profile_home / "AGK-CLIENT.md").read_text(encoding="utf-8") == (
        layout.client("test-client") / "AGENTS.md"
    ).read_text(encoding="utf-8")
    intake_skill = profile_home / "skills" / "client-meeting-intake" / "SKILL.md"
    assert intake_skill.is_file()
    content = intake_skill.read_text(encoding="utf-8")
    assert "Google Drive" in content
    assert "Linear" in content
    assert "cto_approved" in content
    assert "proposal only" in content


def test_client_provider_commands_keep_hermes_and_openrouter_in_profile(
    layout, monkeypatch
):
    monkeypatch.setattr(
        client_control.shutil,
        "which",
        lambda name: f"/tools/{name}",
    )
    workspace = layout.workspace / "clients" / "test-client"

    hermes = client_control.provider_command("hermes", "clientprofile", workspace)
    openrouter = client_control.provider_command(
        "openrouter", "clientprofile", workspace
    )
    codex = client_control.provider_command("codex", "clientprofile", workspace)

    assert hermes == [
        "/tools/hermes",
        "-p",
        "clientprofile",
        "--in",
        str(workspace),
    ]
    assert openrouter[:3] == ["/tools/hermes", "-p", "clientprofile"]
    assert openrouter[-2:] == ["--in", str(workspace)]
    assert "stealth/ox-alpha" in openrouter
    assert codex == ["/tools/codex"]


def test_production_run_is_impossible_while_release_controller_is_disabled(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_to_deploy"
    record["approvals"]["production"] = {"id": "UNTRUSTED"}
    client_control.atomic_yaml(work_path, record)

    with pytest.raises(client_control.ClientError, match="release controller is disabled"):
        client_control.start_run(
            layout,
            Namespace(
                slug="test-client",
                work_id=work["id"],
                action="deploy_production",
                actor="untrusted-cli",
                machine="test-prod-01",
                commit="882ba43",
                before="v1",
                after="v2",
                approval_id="UNTRUSTED",
                rollback_available=True,
            ),
        )
    assert not list((layout.client("test-client") / "state" / "runs").glob("RUN-*.yaml"))


def test_online_doctor_requires_the_exact_client_alias(layout, monkeypatch):
    client_control.create_client(layout, init_args())
    monkeypatch.setattr(
        client_control,
        "composio_connections",
        lambda: {
            "linear": [{"status": "ACTIVE", "word_id": "client-test-client-linear"}],
            "github": [{"status": "ACTIVE", "alias": "client-test-client-github"}],
            "discordbot": [{"status": "ACTIVE", "id": "client-test-client-discordbot"}],
        },
    )

    checks = client_control.doctor_one(layout, "test-client", online=True)
    assert not [message for level, message in checks if level == "fail"]

    monkeypatch.setattr(
        client_control,
        "composio_connections",
        lambda: {
            "linear": [{"status": "ACTIVE", "word_id": "default-linear"}],
            "github": [{"status": "ACTIVE", "word_id": "default-github"}],
            "discordbot": [{"status": "ACTIVE", "word_id": "default-discord"}],
        },
    )
    checks = client_control.doctor_one(layout, "test-client", online=True)
    assert any(
        "alias is missing" in message for level, message in checks if level == "fail"
    )


def test_linear_material_gates_require_structured_https_attachments(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "security_review"
    client_control.atomic_yaml(path, record)

    with pytest.raises(client_control.ClientError, match="requires verified Linear attachments"):
        client_control.linear_sync_plan(layout, "test-client", work["id"])

    updated = client_control.update_evidence(
        layout,
        Namespace(
            slug="test-client", work_id=work["id"], actor="qa-agent",
            pull_request=None, commit=None, engineering_review=None, ci=None,
            qa=None, security=None, security_decision_id=None,
            preview=None, staging_build=None, screenshot=[], validation_step=[],
            linear_attachment=[json.dumps({"title": "Mobile QA", "url": "https://evidence.example/mobile.png"})],
            browser_report=None, qa_session_id=None, rollback_plan=None, risk=None,
            production_health=None, linear_done=False,
        ),
    )
    assert updated["evidence"]["linear_attachments"] == [
        {
            "title": "Mobile QA",
            "subtitle": "AGK verified evidence",
            "url": "https://evidence.example/mobile.png",
        }
    ]
    plan = client_control.linear_sync_plan(layout, "test-client", work["id"])
    assert plan["attachments_required"] is True
    assert plan["attachments"][0]["url"] == "https://evidence.example/mobile.png"


def test_linear_sync_revalidates_persisted_attachment_metadata(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "security_review"
    record["evidence"]["linear_attachments"] = [
        {
            "title": "QA evidence",
            "subtitle": "AGK verified evidence",
            "url": "javascript:alert(1)",
        }
    ]
    client_control.atomic_yaml(path, record)

    with pytest.raises(client_control.ClientError, match="requires an HTTPS URL"):
        client_control.linear_sync_plan(layout, "test-client", work["id"])


def test_linear_evidence_rejects_duplicate_urls_in_the_same_batch(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    attachment = json.dumps(
        {"title": "QA evidence", "url": "https://evidence.example/qa.png"}
    )

    with pytest.raises(client_control.ClientError, match="URLs must be unique"):
        client_control.update_evidence(
            layout,
            Namespace(
                slug="test-client",
                work_id=work["id"],
                actor="qa-agent",
                pull_request=None,
                commit=None,
                engineering_review=None,
                ci=None,
                qa=None,
                security=None,
                security_decision_id=None,
                preview=None,
                staging_build=None,
                screenshot=[],
                validation_step=[],
                linear_attachment=[attachment, attachment],
                browser_report=None,
                qa_session_id=None,
                rollback_plan=None,
                risk=None,
                production_health=None,
                linear_done=False,
            ),
        )


def test_linear_evidence_rejects_canonical_duplicate_urls():
    with pytest.raises(client_control.ClientError, match="URLs must be unique"):
        client_control.validate_linear_attachments(
            [
                {"title": "first", "url": "https://EXAMPLE.com:443/path"},
                {"title": "second", "url": "https://example.com/path"},
            ]
        )


def test_linear_evidence_deduplicates_canonical_urls_across_updates(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)

    def update(title, url):
        return client_control.update_evidence(
            layout,
            Namespace(
                slug="test-client", work_id=work["id"], actor="qa-agent",
                pull_request=None, commit=None, engineering_review=None, ci=None,
                qa=None, security=None, security_decision_id=None,
                preview=None, staging_build=None, screenshot=[], validation_step=[],
                linear_attachment=[json.dumps({"title": title, "url": url})],
                browser_report=None, qa_session_id=None, rollback_plan=None,
                risk=None, production_health=None, linear_done=False,
            ),
        )

    update("first", "https://EXAMPLE.com:443/path")
    record = update("second", "https://example.com/path")
    assert len(record["evidence"]["linear_attachments"]) == 1


def test_linear_sync_is_client_scoped_mapped_and_comment_idempotent(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["linear"]["workflow_state_ids"]["in_progress"] = "state-started"
    client_control.atomic_yaml(config_path, integrations)
    work_path, persisted_work = client_control.load_work(layout, "test-client", work["id"])
    persisted_work["evidence"]["linear_attachments"] = [
        {
            "title": "QA evidence",
            "subtitle": "AGK verified evidence",
            "url": "https://evidence.example/qa.png",
        }
    ]
    client_control.atomic_yaml(work_path, persisted_work)
    calls = []
    comments = []
    attachments = []

    def fake_execute(tool, account, data):
        assert account == "client-test-client-linear"
        calls.append((tool, data))
        if tool == "LINEAR_GET_LINEAR_ISSUE":
            return {
                "data": {
                    "issue": {
                        "identifier": "FOU-142",
                        "team": {"id": "team-id"},
                        "comments": {"nodes": [{"body": body} for body in comments]},
                        "attachments": {"nodes": list(attachments)},
                    }
                }
            }
        if tool == "LINEAR_CREATE_ATTACHMENT":
            attachments.append({"title": data["title"], "url": data["url"]})
        if tool == "LINEAR_CREATE_LINEAR_COMMENT":
            comments.append(data["body"])
        if tool == "LINEAR_RUN_QUERY_OR_MUTATION":
            return {
                "data": {
                    "issue": {
                        "identifier": "FOU-142",
                        "state": {"id": "state-started"},
                    }
                }
            }
        return {"data": {"success": True}}

    monkeypatch.setattr(client_control, "composio_execute", fake_execute)
    first = client_control.linear_sync_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )
    second = client_control.linear_sync_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )

    assert first["comment_created"] is True
    assert first["attachments_created"] == 1
    assert second["comment_created"] is False
    assert second["attachments_created"] == 0
    assert len(comments) == 1
    assert attachments == [{"title": "QA evidence", "url": "https://evidence.example/qa.png"}]
    mutations = [data for tool, data in calls if tool == "LINEAR_RUN_QUERY_OR_MUTATION"]
    assert all(item["variables"]["stateId"] == "state-started" for item in mutations)
    _, persisted = client_control.load_work(layout, "test-client", work["id"])
    assert persisted["linear"]["status_sync"] == "in_progress"


def test_linear_sync_refuses_an_unmapped_state_before_any_external_call(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    monkeypatch.setattr(
        client_control,
        "composio_execute",
        lambda *_args, **_kwargs: pytest.fail(
            "unmapped sync attempted an external call"
        ),
    )

    with pytest.raises(client_control.ClientError, match="no Linear workflow state"):
        client_control.linear_sync_apply(
            layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
        )


def test_discord_review_delivery_is_explicit_and_locally_idempotent(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["discord"]["channels"]["cto_inbox"] = "987654321012345678"
    client_control.atomic_yaml(config_path, integrations)
    calls = []

    def fake_proxy(method, url, account, data=None):
        calls.append((method, url, account, data))
        assert account == "client-test-client-discordbot"
        return {"id": "555555555555555555"}

    monkeypatch.setattr(client_control, "composio_proxy", fake_proxy)
    with pytest.raises(client_control.ClientError, match="requires --yes"):
        client_control.discord_review_apply(
            layout, Namespace(slug="test-client", work_id=work["id"], yes=False)
        )
    assert calls == []

    first = client_control.discord_review_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )
    second = client_control.discord_review_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )

    assert first["created"] is True
    assert first["channel_id"] == "987654321012345678"
    assert second["created"] is False
    assert len(calls) == 1
    payload = calls[0][3]
    labels = {
        button["label"] for row in payload["components"] for button in row["components"]
    }
    assert "REQUEST CHANGES" in labels
    assert "APPROVE" not in labels
    assert "DEPLOY" not in labels
    assert payload["allowed_mentions"] == {"parse": []}

    client_control.request_changes(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            feedback="Fix the retry behavior.",
            actor="cto-user",
        ),
    )
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    revised = client_control.discord_review_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )
    assert revised["created"] is True
    assert len(calls) == 2


def test_discord_review_actions_cannot_bypass_disabled_release_controller(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    prefix = f"agk:review:test-client:{work['id']}"

    with pytest.raises(client_control.ClientError, match="release controller is disabled"):
        client_control.apply_review_action(
            layout,
            Namespace(
                custom_id=prefix + ":approve",
                actor="discord:42",
                decision_id="untrusted-approval",
                feedback=None,
            ),
        )
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_to_deploy"
    client_control.atomic_yaml(work_path, record)
    with pytest.raises(client_control.ClientError, match="release controller is disabled"):
        client_control.apply_review_action(
            layout,
            Namespace(
                custom_id=prefix + ":deploy",
                actor="discord:42",
                decision_id="untrusted-deploy",
                feedback=None,
            ),
        )


def test_soft_autonomy_intent_rejects_negation_and_accepts_french_and_english():
    assert client_control.is_owner_linear_batch_intent("Start all ready Linear work")
    assert client_control.is_owner_linear_batch_intent("Lance toutes les tâches prêtes")
    assert not client_control.is_owner_linear_batch_intent("Do not start all ready Linear work")
    assert not client_control.is_owner_linear_batch_intent("Ne lance pas toutes les tâches prêtes")


def test_blocked_requires_complete_contract_and_resumes_same_context(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    original_session = work["agent"]["session"]
    args = Namespace(
        slug="test-client",
        work_id=work["id"],
        actor="atlas",
        blocked_by="Provider outage",
        already_tried="Retried bounded health probe",
        impact="No external readback is possible",
        need="Provider service recovery",
        resume="Rerun the exact readback",
        no_useful_next_action=True,
    )

    blocked = client_control.block_work(layout, args)
    replay = client_control.block_work(layout, args)
    assert blocked["status"] == "blocked"
    assert replay["blocker"]["fingerprint"] == blocked["blocker"]["fingerprint"]

    resumed = client_control.unblock_work(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            actor="atlas",
            result="Provider health recovered",
        ),
    )
    assert resumed["status"] == blocked["blocker"]["previous_status"]
    assert resumed["agent"]["session"] == original_session
    assert resumed["events"][-1]["event"] == "work.unblocked"


def test_create_work_maps_specialist_to_canonical_identity(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    assert work["agent"]["role"] == "backend-engineer"
    assert work["agent"]["canonical_identity"] == "forge"


def test_accepted_release_controller_binds_exact_pr_head_and_signed_approvals(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["linear"]["release_controller"].update(
        {"enabled": True, "operational_acceptance_verified": True}
    )
    client_control.atomic_yaml(config_path, integrations)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    record["repository"].update(
        {"pull_request": "https://github.example/acme/app/pull/7", "commit": "abc123"}
    )
    client_control.atomic_yaml(work_path, record)

    engineering_args = Namespace(
        slug="test-client",
        work_id=work["id"],
        approval_id="discord-review-7",
        actor="owner-user",
    )
    approved = client_control.approve_work(layout, engineering_args)
    replay = client_control.approve_work(layout, engineering_args)
    assert approved["status"] == "cto_approved"
    assert replay["approvals"]["engineering"]["receipt"] == approved["approvals"]["engineering"]["receipt"]

    production_args = Namespace(
        slug="test-client",
        work_id=work["id"],
        approval_id="discord-production-8",
        actor="owner-user",
    )
    authorized = client_control.authorize_deploy(layout, production_args)
    assert authorized["status"] == "ready_to_deploy"
    assert authorized["approvals"]["production"]["head_sha"] == "abc123"
    assert authorized["approvals"]["production"]["receipt"]

    with pytest.raises(client_control.ClientError, match="approved PR head"):
        client_control.start_run(
            layout,
            Namespace(
                slug="test-client",
                work_id=work["id"],
                action="deploy_production",
                actor="release-engineer",
                machine="prod-01",
                commit="different",
                before="v1",
                after="v2",
                approval_id="discord-production-8",
                rollback_available=True,
            ),
        )
    run = client_control.start_run(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            action="deploy_production",
            actor="release-engineer",
            machine="prod-01",
            commit="abc123",
            before="v1",
            after="v2",
            approval_id="discord-production-8",
            rollback_available=True,
        ),
    )
    assert run["status"] == "running"


def test_owner_batch_authorizes_each_ready_non_production_work_with_thread_and_receipt(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client",
            issue="FOU-177",
            title="Ready batch item",
            role="frontend-engineer",
            provider="hermes",
            repo=repository,
            branch=None,
            session=None,
            target="staging",
        ),
    )
    path, record = client_control.load_work(layout, "test-client", work["id"])
    attach_verified_linear_snapshot(layout, "test-client", record, "FOU-177")
    client_control.atomic_yaml(path, record)
    integrations_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(integrations_path)
    integrations["linear"]["delivery_project_id"] = "project-id"
    integrations["discord"].update(
        {
            "owner_user_id": "owner-1",
            "guild_id": "123456789012345678",
            "channels": {"dev_requests": "123456789012345679"},
        }
    )
    client_control.atomic_yaml(integrations_path, integrations)
    timestamp = client_control.dt.datetime.now(client_control.dt.timezone.utc).isoformat()

    def fake_get(_layout, _slug, endpoint):
        if endpoint == "/channels/123456789012345679":
            return {"guild_id": "123456789012345678"}
        return {
            "channel_id": "123456789012345679",
            "author": {"id": "owner-1", "bot": False},
            "content": "Start all ready Linear work",
            "timestamp": timestamp,
        }

    monkeypatch.setattr(client_control, "discord_client_get", fake_get)
    monkeypatch.setattr(
        client_control,
        "_ensure_linear_issue_thread",
        lambda *_args, **_kwargs: {
            "channel_id": "123456789012345679",
            "starter_message_id": "223456789012345679",
            "thread_id": "323456789012345679",
        },
    )
    result = client_control.authorize_linear_batch(
        layout,
        Namespace(
            slug="test-client",
            channel_id="123456789012345679",
            message_id="423456789012345679",
            yes=True,
        ),
    )
    assert result["authorized"] == [
        {
            "work_id": work["id"],
            "issue": "FOU-177",
            "thread_id": "323456789012345679",
        }
    ]
    _, authorized = client_control.load_work(layout, "test-client", work["id"])
    assert authorized["status"] == "todo"
    assert authorized["authorization"]["source"] == "discord_batch"
    assert authorized["authorization"]["receipt"]
    client_control.validate_work_start_record(
        layout, "test-client", work["id"], authorized
    )


def test_batch_skips_work_with_a_tampered_linear_snapshot_receipt(layout):
    client_control.create_client(layout, init_args())
    repository = declare_repository(layout, "test-client")
    work = client_control.create_work(
        layout,
        Namespace(
            slug="test-client", issue="FOU-188", title="Tampered snapshot",
            role="backend-engineer", provider="hermes", repo=repository,
            branch=None, session=None, target="staging",
        ),
    )
    path, record = client_control.load_work(layout, "test-client", work["id"])
    attach_verified_linear_snapshot(layout, "test-client", record, "FOU-188")
    receipt = layout.system / record["context"]["linear_snapshot"]["receipt"]
    receipt.chmod(0o600)
    payload = json.loads(receipt.read_text())
    payload["signature"] = "0" * 64
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    receipt.chmod(0o400)
    client_control.atomic_yaml(path, record)

    contract = client_control._batch_work_contract(layout, "test-client")

    assert contract["eligible"] == []
    assert contract["skipped"] == [
        {"work_id": work["id"], "reason": "linear-snapshot-invalid"}
    ]


def test_production_run_rejects_a_tampered_signed_authorization(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["linear"]["release_controller"].update(
        {"enabled": True, "operational_acceptance_verified": True}
    )
    client_control.atomic_yaml(config_path, integrations)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    record["repository"].update(
        {"pull_request": "https://github.example/acme/app/pull/9", "commit": "def456"}
    )
    client_control.atomic_yaml(work_path, record)
    client_control.approve_work(
        layout,
        Namespace(
            slug="test-client", work_id=work["id"],
            approval_id="engineering-9", actor="owner-user",
        ),
    )
    authorized = client_control.authorize_deploy(
        layout,
        Namespace(
            slug="test-client", work_id=work["id"],
            approval_id="production-9", actor="owner-user",
        ),
    )
    receipt = layout.system / authorized["approvals"]["production"]["receipt"]
    receipt.chmod(0o600)
    payload = json.loads(receipt.read_text())
    payload["signature"] = "f" * 64
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    receipt.chmod(0o400)

    with pytest.raises(client_control.ClientError, match="signature is invalid"):
        client_control.start_run(
            layout,
            Namespace(
                slug="test-client", work_id=work["id"], action="deploy_production",
                actor="release-engineer", machine="prod-01", commit="def456",
                before="v1", after="v2", approval_id="production-9",
                rollback_available=True,
            ),
        )
