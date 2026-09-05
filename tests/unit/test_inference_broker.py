"""Inference boundary tests use local fake HTTP only, never a paid provider."""

from __future__ import annotations

import copy
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import sys
import threading
import time
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_module(name):
    spec = importlib.util.spec_from_file_location("station_inference_" + name,
                                                ROOT / "runtime" / "inference" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


broker = load_module("broker")
token_helper = load_module("token")
preflight = load_module("preflight")
CAPABILITY = "a" * 64
SOURCE_TOKEN = "source-secret-never-in-target"
GRANT = {"zone_id": "acme-dev", "uid": 2101,
         "token_sha256": hashlib.sha256(CAPABILITY.encode()).hexdigest()}
CONFIG = {"schema_version": 1, "port": 8791,
          "source": {"operator": "agk-station", "hermes_home": "/home/agk-station/.hermes"},
          "grants": [GRANT]}


def frame(value):
    return b"data: " + json.dumps(value).encode() + b"\n\n"


TEXT = frame({"type": "response.output_text.delta", "delta": "Hello from the fake model"})
DONE = frame({"type": "response.completed", "response": {"status": "completed", "output": []}})


class Source:
    def __init__(self):
        self.calls = 0
        self.model = "gpt-test"
        self.failure = None
        self.token = SOURCE_TOKEN

    def resolve(self):
        self.calls += 1
        if self.failure:
            raise self.failure
        return {"model": self.model, "headers": {"Authorization": "Bearer " + self.token,
                "Content-Type": "application/json", "Accept": "text/event-stream",
                "User-Agent": "HermesAgent/test", "ChatGPT-Account-ID": "source-account"}}


@pytest.fixture
def harness():
    state = SimpleNamespace(requests=[], chunks=[TEXT, DONE], status=200, delay=0,
                            content_type="text/event-stream", encoding=None, closed=0,
                            source=Source(), config=copy.deepcopy(CONFIG))

    class Upstream(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            state.requests.append({"path": self.path, "body": json.loads(raw),
                                   "headers": dict(self.headers.items())})
            self.send_response(state.status)
            self.send_header("Content-Type", state.content_type)
            self.send_header("Connection", "close")
            self.send_header("Set-Cookie", "source-secret-cookie")
            self.send_header("Location", "https://example.invalid/secret")
            if state.encoding:
                self.send_header("Content-Encoding", state.encoding)
            self.end_headers()
            try:
                for chunk in state.chunks:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    if state.delay:
                        time.sleep(state.delay)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)

    def connect(payload, headers):
        connection = http.client.HTTPConnection("127.0.0.1", upstream.server_port, timeout=3)
        connection.request("POST", broker.UPSTREAM_PATH, payload, headers)
        response = connection.getresponse()
        original_close = response.close

        def close():
            state.closed += 1
            original_close()
        response.close = close
        return connection, response

    server = broker.InferenceServer(0, config_loader=lambda: state.config,
                                    source=state.source, upstream=connect)
    state.server = server
    threads = [threading.Thread(target=service.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
               for service in (upstream, server)]
    for thread in threads:
        thread.start()

    def request(method="POST", path="/responses", body=None, headers=None, auth=True):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        values = {"Content-Type": "application/json"}
        if auth:
            values["Authorization"] = "Bearer " + CAPABILITY
        values.update(headers or {})
        raw = body if isinstance(body, bytes) else json.dumps(
            {"model": "hermes-default", "input": "hello"} if body is None else body).encode()
        connection.request(method, path, raw if method == "POST" else None, values)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    state.request = request
    yield state
    for service in (server, upstream):
        service.shutdown()
        service.server_close()
    for thread in threads:
        thread.join(timeout=3)


def test_health_is_not_authentication_or_provider_acceptance(harness):
    status, _, raw = harness.request("GET", "/health", auth=False)
    assert status == 200
    assert json.loads(raw) == {"status": "listening", "provider_readiness": "not_checked"}
    assert harness.source.calls == 0 and not harness.requests


def test_real_http_text_stream_has_no_source_headers(harness):
    status, headers, raw = harness.request()
    assert status == 200 and raw == TEXT + DONE
    assert headers["Content-Type"] == "text/event-stream"
    assert "Set-Cookie" not in headers and "Location" not in headers
    assert SOURCE_TOKEN.encode() not in raw
    assert harness.requests[0]["path"] == broker.UPSTREAM_PATH
    assert harness.requests[0]["body"]["model"] == "gpt-test"
    assert harness.closed >= 1


def test_stream_yields_first_event_before_upstream_finishes(harness):
    harness.delay = 0.3
    connection = http.client.HTTPConnection("127.0.0.1", harness.server.server_port, timeout=2)
    connection.request("POST", "/responses", json.dumps({"model": "hermes-default", "input": "hi"}),
                       {"Authorization": "Bearer " + CAPABILITY, "Content-Type": "application/json"})
    start = time.monotonic()
    response = connection.getresponse()
    assert response.readline() == TEXT.splitlines(keepends=True)[0]
    assert time.monotonic() - start < 0.25
    response.read()
    connection.close()


def test_function_call_and_output_roundtrip_are_not_executed_by_broker(harness):
    call = {"type": "function_call", "name": "local_test_tool", "arguments": '{"x":1}',
            "call_id": "call_test"}
    harness.chunks = [frame({"type": "response.output_item.done", "item": call}), DONE]
    body = {"model": "hermes-default", "input": "call local tool", "tools": [
        {"type": "function", "name": "local_test_tool", "parameters": {"type": "object"}}]}
    assert harness.request(body=body)[2] == b"".join(harness.chunks)
    body["input"] = [call, {"type": "function_call_output", "call_id": "call_test", "output": "2"}]
    assert harness.request(body=body)[0] == 200
    assert harness.requests[-1]["body"]["input"] == body["input"]


@pytest.mark.parametrize("path", ["/responses", "/v1/responses", "/models", "/v1/models"])
def test_inference_endpoint_aliases(harness, path):
    assert harness.request("GET" if path.endswith("models") else "POST", path)[0] == 200


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic abc", "Bearer " + "B" * 64])
def test_invalid_capability_never_reads_source_or_contacts_upstream(harness, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    assert harness.request(headers=headers, auth=False)[0] == 401
    assert harness.source.calls == 0 and not harness.requests


def test_revocation_takes_effect_on_next_request(harness):
    assert harness.request()[0] == 200
    harness.config["grants"] = []
    assert harness.request()[0] == 401
    assert len(harness.requests) == 1


@pytest.mark.parametrize("path", ["/v1/chat/completions", "/sessions", "/files", "/responses/old-id",
                                  "/tools", "/responses?url=http://localhost", "//evil.invalid/responses"])
def test_agent_storage_and_arbitrary_routes_not_available(harness, path):
    assert harness.request(path=path)[0] == 404
    assert harness.source.calls == 0 and not harness.requests


def test_client_cannot_choose_upstream_credentials_or_identity(harness):
    assert harness.request(headers={"ChatGPT-Account-ID": "attacker", "Cookie": "evil",
        "OpenAI-Organization": "attacker", "OpenAI-Project": "attacker", "session_id": "evil",
        "User-Agent": "attacker", "X-Forwarded-Host": "evil.invalid"})[0] == 200
    headers = harness.requests[0]["headers"]
    assert headers["Authorization"] == "Bearer " + SOURCE_TOKEN
    assert headers["ChatGPT-Account-ID"] == "source-account"
    assert headers["User-Agent"] == "HermesAgent/test"
    assert not {"Cookie", "OpenAI-Organization", "OpenAI-Project", "session_id", "X-Forwarded-Host"} & headers.keys()


@pytest.mark.parametrize("body", [b"{broken", b"[]", b'{"model":"a","model":"b"}',
                                  b'{"input":NaN}', b"\xff"])
def test_malformed_json_is_redacted(harness, body):
    assert harness.request(body=body)[0] == 400
    assert not harness.requests


@pytest.mark.parametrize("field,value", [("previous_response_id", "resp_other_zone"),
    ("conversation", "conv_source"), ("background", True), ("url", "https://evil.invalid"),
    ("base_url", "http://127.0.0.1:1"), ("extra_headers", {"Authorization": "evil"}),
    ("extra_body", {"store": True}), ("metadata", {"account": "other"})])
def test_persistence_and_endpoint_overrides_are_rejected(harness, field, value):
    body = {"model": "hermes-default", "input": "hello", field: value}
    assert harness.request(body=body)[0] == 400
    assert not harness.requests


@pytest.mark.parametrize("tools", [[{"type": kind}] for kind in
    ("web_search", "file_search", "computer_use_preview", "mcp", "code_interpreter", "image_generation")])
def test_provider_hosted_tools_are_not_exposed(harness, tools):
    assert harness.request(body={"model": "hermes-default", "input": "hi", "tools": tools})[0] == 400
    assert not harness.requests


@pytest.mark.parametrize("item", [{"type": "item_reference", "id": "other"},
    {"type": "message", "content": [{"type": "input_file", "file_id": "other"}]},
    {"type": "message", "content": [{"type": "input_image", "file_id": "other"}]}])
def test_provider_stored_input_is_not_exposed(harness, item):
    assert harness.request(body={"model": "hermes-default", "input": [item]})[0] == 400
    assert not harness.requests


def test_codex_contract_and_zone_cache_namespace(harness):
    body = {"model": "gpt-test", "input": "hi", "store": True, "stream": False,
            "max_output_tokens": 100, "prompt_cache_retention": "24h", "prompt_cache_key": "same"}
    assert harness.request(body=body)[0] == 200
    sent = harness.requests[0]["body"]
    assert sent["store"] is False and sent["stream"] is True
    assert "max_output_tokens" not in sent and "prompt_cache_retention" not in sent
    assert sent["prompt_cache_key"] == hashlib.sha256(b"acme-dev:same").hexdigest()


def test_models_and_default_refresh_between_requests(harness):
    assert {entry["id"] for entry in json.loads(harness.request("GET", "/models")[2])["data"]} == {
        "hermes-default", "gpt-test"}
    harness.source.model, harness.source.token = "gpt-new-default", "new-source-token"
    assert harness.request()[0] == 200
    assert harness.requests[-1]["body"]["model"] == "gpt-new-default"
    assert harness.requests[-1]["headers"]["Authorization"] == "Bearer new-source-token"
    assert harness.request(body={"model": "gpt-test", "input": "hi"})[0] == 400


def test_source_transport_switch_is_clear_not_silent_fallback(harness):
    harness.source.failure = broker.BrokerError("source_provider_not_supported")
    status, _, raw = harness.request()
    assert status == 503 and b"source_provider_not_supported" in raw
    assert not harness.requests


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 403, 429, 500])
def test_upstream_errors_and_redirects_never_expose_body_or_headers(harness, status):
    harness.status, harness.chunks = status, [b"provider token " + SOURCE_TOKEN.encode()]
    observed, headers, raw = harness.request()
    assert observed == (status if status in (400, 401, 403, 429) else 502)
    assert b"upstream_request_failed" in raw and SOURCE_TOKEN.encode() not in raw
    assert "Location" not in headers and "Set-Cookie" not in headers
    assert len(harness.requests) == 1 and harness.closed >= 1


@pytest.mark.parametrize("kind", ["error", "response.failed", "response.incomplete"])
def test_http_200_sse_errors_do_not_leak_provider_diagnostics(harness, kind):
    harness.chunks = [frame({"type": kind, "error": {"message": SOURCE_TOKEN},
                            "response": {"error": {"message": SOURCE_TOKEN}}})]
    status, _, raw = harness.request()
    assert status == 200 and b"upstream_inference_failed" in raw
    assert SOURCE_TOKEN.encode() not in raw


@pytest.mark.parametrize("raw", [
    b'event: error\ndata: {"message":"SYNTHETIC_SECRET"}\n\n',
    b'event: response.failed\ndata: {"response":{"error":{"message":"SYNTHETIC_SECRET"}}}\n\n',
    b'event: response.completed\ndata: {"type":"response.completed","response":{"status":"failed","error":{"message":"SYNTHETIC_SECRET"}}}\n\n',
])
def test_event_name_and_nested_response_failures_are_redacted(raw):
    sanitized = broker.safe_event(raw)
    assert b"SYNTHETIC_SECRET" not in sanitized
    assert b"upstream_inference_failed" in sanitized


def test_revocation_during_source_resolution_prevents_upstream(harness):
    original = harness.source.resolve
    def revoke():
        result = original()
        harness.config["grants"] = []
        return result
    harness.source.resolve = revoke
    assert harness.request()[0] == 401
    assert not harness.requests


@pytest.mark.parametrize("headers", [{"Transfer-Encoding": "chunked"}, {"Content-Encoding": "gzip"},
                                     {"Content-Type": "text/plain"}, {"Content-Length": "99999999"},
                                     {"Origin": "https://example.com"}, {"Host": "evil.invalid"}])
def test_framing_origin_and_rebinding_are_rejected(harness, headers):
    assert harness.request(headers=headers)[0] in (400, 403, 413)
    assert not harness.requests


def test_duplicate_auth_and_length_rejected_before_upstream(harness):
    for duplicate in ("Authorization: Bearer " + CAPABILITY, "Content-Length: 2"):
        with socket.create_connection(("127.0.0.1", harness.server.server_port), timeout=2) as connection:
            raw = (f"POST /responses HTTP/1.1\r\nHost: 127.0.0.1:{harness.server.server_port}\r\n"
                   f"Authorization: Bearer {CAPABILITY}\r\nContent-Type: application/json\r\n"
                   f"Content-Length: 2\r\n{duplicate}\r\n\r\n{{}}")
            connection.sendall(raw.encode())
            response = connection.recv(4096)
            assert b"401" in response or b"400" in response
    assert not harness.requests


def test_client_disconnect_closes_upstream(harness):
    harness.chunks = [TEXT] * 30
    harness.delay = 0.02
    connection = http.client.HTTPConnection("127.0.0.1", harness.server.server_port, timeout=2)
    connection.request("POST", "/responses", json.dumps({"model": "hermes-default", "input": "hi"}),
                       {"Authorization": "Bearer " + CAPABILITY, "Content-Type": "application/json"})
    response = connection.getresponse()
    response.readline()
    response.close()
    connection.close()
    deadline = time.monotonic() + 2
    while harness.closed == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert harness.closed >= 1


def test_connection_worker_limit_does_not_spawn_more_requests(harness):
    for _ in range(broker.MAX_WORKERS):
        assert harness.server.slots.acquire(blocking=False)
    try:
        with socket.create_connection(("127.0.0.1", harness.server.server_port), timeout=1) as connection:
            connection.sendall(b"GET /health HTTP/1.1\r\n")
            assert b"503" in connection.recv(1024)
        assert harness.source.calls == 0
    finally:
        for _ in range(broker.MAX_WORKERS):
            harness.server.slots.release()


def test_partial_headers_and_body_have_absolute_deadlines(harness, monkeypatch):
    monkeypatch.setattr(broker, "CLIENT_TIMEOUT", 0.1)
    with socket.create_connection(("127.0.0.1", harness.server.server_port), timeout=1) as connection:
        connection.sendall(b"GET /")
        assert connection.recv(1024) == b""
    with socket.create_connection(("127.0.0.1", harness.server.server_port), timeout=1) as connection:
        connection.sendall((f"POST /responses HTTP/1.1\r\nHost: 127.0.0.1:{harness.server.server_port}\r\n"
                            f"Authorization: Bearer {CAPABILITY}\r\nContent-Type: application/json\r\n"
                            "Content-Length: 100\r\n\r\n{").encode())
        assert b"502" in connection.recv(1024)
    assert harness.source.calls == 0 and not harness.requests


def test_stream_limits_bound_chunk_and_event_buffer(monkeypatch):
    class Response:
        def __init__(self, chunks):
            self.chunks = iter(chunks)
            self.requests = []
        def read1(self, size):
            self.requests.append(size)
            return next(self.chunks, b"")
    response = Response([TEXT[:8], TEXT[8:], DONE])
    assert list(broker.stream_events(response, deadline=time.monotonic() + 1)) == [TEXT, DONE]
    assert set(response.requests) == {broker.CHUNK_SIZE}
    monkeypatch.setattr(broker, "MAX_EVENT", 50)
    with pytest.raises(broker.BrokerError, match="upstream_event_limit"):
        list(broker.stream_events(Response([b"x" * 51]), deadline=time.monotonic() + 1))
    with pytest.raises(broker.BrokerError, match="incomplete_upstream_event"):
        list(broker.stream_events(Response([b"data: partial"]), deadline=time.monotonic() + 1))
    with pytest.raises(broker.BrokerError, match="upstream_stream_timeout"):
        list(broker.stream_events(Response([TEXT]), deadline=time.monotonic() - 1))
    monkeypatch.setattr(broker, "MAX_STREAM", 1)
    with pytest.raises(broker.BrokerError, match="upstream_stream_limit"):
        list(broker.stream_events(Response([TEXT]), deadline=time.monotonic() + 1))


def test_native_source_helper_timeout_kills_reaps_and_never_prints_auth(monkeypatch, capsys):
    children = []
    class Child:
        def __init__(self, argv, **kwargs):
            self.argv, self.kwargs, self.returncode = argv, kwargs, None
            self.write_fd = os.dup(kwargs["pass_fds"][0])
            self.killed, self.waited = False, False
            children.append(self)
        def poll(self):
            return self.returncode
        def kill(self):
            self.killed = True
            self.returncode = -9
            os.close(self.write_fd)
        def wait(self, timeout=None):
            self.waited = True
            return self.returncode
    monkeypatch.setattr(broker.subprocess, "Popen", Child)
    monkeypatch.setattr(broker, "SOURCE_TIMEOUT", 0.02)
    source = broker.NativeSource()
    with pytest.raises(broker.BrokerError, match="source_timeout"):
        source.resolve()
    child = children[0]
    assert child.killed and child.waited
    assert child.kwargs["stdout"] == broker.subprocess.DEVNULL
    assert child.kwargs["stderr"] == broker.subprocess.DEVNULL
    assert child.kwargs["env"]["HERMES_HOME"] == "/home/agk-station/.hermes"
    assert "--source-fd" in child.argv
    assert source.lock.acquire(blocking=False)
    source.lock.release()
    assert capsys.readouterr().out == ""


def test_fixed_https_transport_ignores_proxy_environment(monkeypatch):
    calls = []
    class Connection:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
        def request(self, *args):
            calls.append(args)
        def getresponse(self):
            return SimpleNamespace(status=307)
        def close(self):
            pass
    monkeypatch.setenv("HTTPS_PROXY", "http://evil.invalid")
    monkeypatch.setattr(broker.http.client, "HTTPSConnection", Connection)
    _, response = broker.open_upstream(b"{}", {"Authorization": "Bearer fake"})
    assert calls[0][0] == ("chatgpt.com", 443)
    assert calls[1][:2] == ("POST", "/backend-api/codex/responses")
    assert response.status == 307 and len(calls) == 2


def account(uid):
    return SimpleNamespace(pw_dir=f"/var/lib/station/zones/acme-dev/home", pw_uid=uid)


def test_grant_schema_and_exact_canonical_identity():
    assert broker.validate_config(CONFIG, account_lookup=account) == CONFIG
    changed = copy.deepcopy(CONFIG)
    changed["grants"][0]["zone_id"] = "other-zone"
    with pytest.raises(broker.BrokerError, match="invalid_grant_identity"):
        broker.validate_config(changed, account_lookup=account)


@pytest.mark.parametrize("change", [lambda v: v.update(schema_version=True),
    lambda v: v.update(port=True), lambda v: v.update(source={"operator": "other"}),
    lambda v: v.update(extra="not allowed"), lambda v: v.update(grants="not a list"),
    lambda v: v["grants"].append(copy.deepcopy(v["grants"][0])),
    lambda v: v["grants"][0].update(uid=0), lambda v: v["grants"][0].update(uid=True),
    lambda v: v["grants"][0].update(zone_id="../../private"),
    lambda v: v["grants"][0].update(token_sha256="invalid")])
def test_invalid_config_and_duplicate_grants(change):
    value = copy.deepcopy(CONFIG)
    change(value)
    with pytest.raises(broker.BrokerError):
        broker.validate_config(value, account_lookup=account)


@pytest.fixture
def protected_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG))
    path.chmod(0o640)
    # Isolate leaf checks from the test runner's deliberately temporary parent.
    monkeypatch.setattr(broker, "_open_directory", lambda *args: os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY))
    return path


@pytest.mark.parametrize("mutation", ["mode", "owner", "symlink", "hardlink", "fifo", "size"])
def test_config_file_owner_mode_type_link_and_size_are_enforced(protected_file, mutation):
    path = protected_file
    owner = os.getuid()
    if mutation == "mode":
        path.chmod(0o666)
    elif mutation == "owner":
        owner += 1
    elif mutation == "symlink":
        source = path.with_name("actual")
        path.rename(source)
        path.symlink_to(source)
    elif mutation == "hardlink":
        os.link(path, path.with_name("alias"))
    elif mutation == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif mutation == "size":
        path.write_bytes(b"x" * (broker.MAX_CONFIG + 1))
    with pytest.raises((OSError, broker.BrokerError)):
        broker.protected_read(path, owner=owner)


def test_config_regular_private_parent_leaf_acceptance(protected_file):
    assert json.loads(broker.protected_read(protected_file, owner=os.getuid())) == CONFIG


@pytest.fixture
def zone_token(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    uid = os.getuid() or 2101
    monkeypatch.setattr(token_helper.os, "geteuid", lambda: uid)
    monkeypatch.setattr(token_helper.os, "getuid", lambda: uid)
    monkeypatch.setattr(token_helper.pwd, "getpwuid", account)
    monkeypatch.setattr(token_helper, "_open_directory", lambda *args: os.open(state, os.O_RDONLY | os.O_DIRECTORY))
    # CI may run as root: fake only expected ownership, retain all actual modes/types.
    if os.stat(state).st_uid != uid:
        os.chown(state, uid, -1)
        original = os.open
        def owned_open(*args, **kwargs):
            fd = original(*args, **kwargs)
            if args[0] == "token" and args[1] & os.O_CREAT:
                os.fchown(fd, uid, -1)
            return fd
        monkeypatch.setattr(token_helper.os, "open", owned_open)
        original_mkdir = os.mkdir
        def owned_mkdir(*args, **kwargs):
            original_mkdir(*args, **kwargs)
            if args[0] == "model-access":
                os.chown("model-access", uid, -1, dir_fd=kwargs["dir_fd"])
        monkeypatch.setattr(token_helper.os, "mkdir", owned_mkdir)
    return state, uid


def test_zone_token_create_digest_read_and_no_source_secret_copy(zone_token, monkeypatch):
    state, uid = zone_token
    monkeypatch.setenv("HOME", "/home/agk-station")
    monkeypatch.setenv("HERMES_HOME", "/home/agk-station/.hermes")
    result = token_helper.capability("create")
    token = token_helper.capability()
    assert len(token) == 64 and result["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(result) and result == token_helper.capability("digest")
    assert result["zone_id"] == "acme-dev" and result["uid"] == uid
    assert stat.S_IMODE((state / "model-access/token").stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        token_helper.capability("create")


@pytest.mark.parametrize("mutation", ["mode", "hardlink", "symlink", "format", "directory_mode"])
def test_zone_capability_negative_filesystem_cases(zone_token, mutation):
    state, _ = zone_token
    token_helper.capability("create")
    path = state / "model-access/token"
    if mutation == "mode":
        path.chmod(0o644)
    elif mutation == "hardlink":
        os.link(path, path.with_name("alias"))
    elif mutation == "symlink":
        path.rename(path.with_name("actual"))
        path.symlink_to("actual")
    elif mutation == "format":
        path.write_bytes(b"not a capability")
    else:
        path.parent.chmod(0o755)
    with pytest.raises((OSError, token_helper.TokenError)):
        token_helper.capability()


def test_token_helper_rejects_root_and_non_zone_before_any_path(monkeypatch):
    monkeypatch.setattr(token_helper.os, "geteuid", lambda: 0)
    with pytest.raises(token_helper.TokenError):
        token_helper.capability()
    monkeypatch.setattr(token_helper.os, "geteuid", lambda: 2101)
    monkeypatch.setattr(token_helper.os, "getuid", lambda: 2101)
    monkeypatch.setattr(token_helper.pwd, "getpwuid", lambda _: SimpleNamespace(pw_dir="/home/agk-station"))
    with pytest.raises(token_helper.TokenError):
        token_helper.capability()


def test_native_source_uses_only_persisted_codex_default_and_native_headers(monkeypatch, tmp_path, capsys):
    model = {"provider": "openai-codex", "default": "gpt-test"}
    calls = []
    monkeypatch.setattr(broker, "source_identity", lambda: SimpleNamespace(pw_uid=2100))
    monkeypatch.setattr(broker.logging, "disable", lambda _: None)
    monkeypatch.setattr(broker, "trusted_hermes_path", lambda _: tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "hermes_cli.config", SimpleNamespace(load_config_readonly=lambda: {"model": model}))
    def resolve(**kwargs):
        print(SOURCE_TOKEN)
        calls.append(kwargs)
        return {"provider": "openai-codex", "api_mode": "codex_responses",
                "base_url": broker.UPSTREAM_BASE, "api_key": SOURCE_TOKEN}
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", SimpleNamespace(resolve_runtime_provider=resolve))
    monkeypatch.setitem(sys.modules, "agent.codex_headers", SimpleNamespace(codex_cloudflare_headers=lambda *a, **k: {
        "originator": "hermes-agent", "ChatGPT-Account-ID": "source", "X-Unsafe": "drop"}))
    result = broker.resolve_source_native()
    assert result["model"] == "gpt-test" and result["headers"]["Authorization"] == "Bearer " + SOURCE_TOKEN
    assert "X-Unsafe" not in result["headers"]
    assert calls == [{"requested": "openai-codex", "target_model": "gpt-test"}]
    assert SOURCE_TOKEN not in capsys.readouterr().out
    model["provider"] = "anthropic"
    with pytest.raises(broker.BrokerError, match="source_provider_not_supported"):
        broker.resolve_source_native()
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", ["file_write", "directory_write", "symlink", "hardlink", "pyc_write"])
def test_source_descendants_and_bytecode_are_checked(tmp_path, monkeypatch, mutation):
    source = tmp_path / "source"
    source.mkdir(mode=0o755)
    child = source / "hermes_cli"
    child.mkdir(mode=0o755)
    module = child / "config.py"
    module.write_text("pass\n")
    module.chmod(0o644)
    monkeypatch.setattr(broker, "_open_directory", lambda *args: os.open(source, os.O_RDONLY | os.O_DIRECTORY))
    broker.validate_source_tree(source, os.getuid())
    if mutation == "file_write":
        module.chmod(0o666)
    elif mutation == "directory_write":
        child.chmod(0o777)
    elif mutation == "symlink":
        module.rename(child / "actual.py")
        module.symlink_to("actual.py")
    elif mutation == "hardlink":
        os.link(module, child / "alias.py")
    else:
        cache = child / "__pycache__"
        cache.mkdir(mode=0o755)
        pyc = cache / "config.cpython.pyc"
        pyc.write_bytes(b"fake bytecode")
        pyc.chmod(0o666)
    with pytest.raises(broker.BrokerError, match="unsafe_hermes_source"):
        broker.validate_source_tree(source, os.getuid())


@pytest.fixture
def trust_tree(tmp_path, monkeypatch):
    source, python = tmp_path / "source", tmp_path / "python"
    source.mkdir(mode=0o755)
    python.mkdir(mode=0o755)
    # The test runner may put fixtures under world-writable /tmp; normalize
    # only ancestor metadata in this synthetic test, never managed descendants.
    original_stat = os.stat
    ancestors = set(tmp_path.parts[1:])
    def ancestor_stat(path, *args, **kwargs):
        st = original_stat(path, *args, **kwargs)
        if kwargs.get("dir_fd") is not None and path in ancestors:
            values = list(st)
            values[0] &= ~0o022
            return os.stat_result(values)
        return st
    monkeypatch.setattr(preflight.os, "stat", ancestor_stat)
    return source, python, (source, python), (0, os.getuid())


def test_preflight_allows_only_confined_interpreter_links(trust_tree):
    source, python, roots, owners = trust_tree
    executable = python / "python3.11"
    executable.write_text("synthetic executable")
    executable.chmod(0o755)
    link = source / "python"
    link.symlink_to(executable)
    assert preflight.safe_resolve(link, roots, owners) == executable
    observed = preflight.inspect_tree(source, roots, owners)
    assert observed["links"] == 1
    link.unlink()
    link.symlink_to("/etc/passwd")
    with pytest.raises(preflight.PreflightError, match="code_link_escape"):
        preflight.inspect_tree(source, roots, owners)


def test_native_web_node_modules_are_not_python_import_roots(trust_tree, monkeypatch):
    source, _, roots, owners = trust_tree
    web = source / 'web'
    web.mkdir(mode=0o755)
    npm = web / 'node_modules'
    npm.mkdir(mode=0o755)
    (npm / 'parser').symlink_to('/outside')
    assert preflight.inspect_tree(source, roots, owners)['links'] == 0
    monkeypatch.setattr(broker, '_open_directory', lambda *args: os.open(source, os.O_RDONLY | os.O_DIRECTORY))
    broker.validate_source_tree(source, os.getuid())
    (source / 'module.py').symlink_to(npm / 'parser')
    with pytest.raises(preflight.PreflightError, match='code_link_escape'):
        preflight.inspect_tree(source, roots, owners)


def test_reviewed_base_python_setuptools_shim(trust_tree):
    source, python, roots, owners = trust_tree
    shim = python / 'distutils-precedence.pth'
    shim.write_text("import os; var = 'SETUPTOOLS_USE_DISTUTILS'; enabled = os.environ.get(var, 'local') == 'local'; enabled and __import__('_distutils_hack').add_shim(); \n")
    shim.chmod(0o644)
    preflight.validate_startup_file(shim, source, roots, owners)
    shim.write_text(shim.read_text() + 'import arbitrary_startup\n')
    with pytest.raises(preflight.PreflightError, match='unreviewed_python_startup'):
        preflight.validate_startup_file(shim, source, roots, owners)


def test_token_uses_traverse_only_ancestor_descriptors(tmp_path, monkeypatch):
    traverse = getattr(os, 'O_PATH', 0x200000)
    monkeypatch.setattr(token_helper.os, 'O_PATH', traverse, raising=False)
    calls, real_open = [], os.open
    def record(path, flags, **kwargs):
        calls.append((path, flags))
        # macOS has no O_PATH; preserve the requested Linux flags for assertion.
        return real_open(path, flags & ~traverse, **kwargs)
    monkeypatch.setattr(token_helper.os, 'open', record)
    monkeypatch.setattr(token_helper.os, 'fstat', lambda fd: SimpleNamespace(st_uid=os.getuid(), st_mode=0o40700))
    fd = token_helper._open_directory(str(tmp_path), os.getuid())
    os.close(fd)
    assert all(flags & traverse for _, flags in calls[:-1])
    assert not calls[-1][1] & traverse


def test_preflight_rejects_excluded_tree_links_and_loops(trust_tree):
    source, _, roots, owners = trust_tree
    excluded = source / ".git"
    excluded.mkdir(mode=0o755)
    (excluded / "secret.py").write_text("pass")
    link = source / "module.py"
    link.symlink_to(excluded / "secret.py")
    with pytest.raises(preflight.PreflightError, match="code_link_escape"):
        preflight.safe_resolve(link, roots, owners)
    link.unlink()
    link.symlink_to(link.name)
    with pytest.raises(preflight.PreflightError, match="code_link_cycle"):
        preflight.safe_resolve(link, roots, owners)


@pytest.mark.parametrize("bad_kind", ["mode", "fifo", "parent_link"])
def test_preflight_rejects_mutable_or_special_code(trust_tree, bad_kind):
    source, _, roots, owners = trust_tree
    module = source / "module.py"
    if bad_kind == "fifo":
        os.mkfifo(module)
    else:
        module.write_text("pass")
        module.chmod(0o666 if bad_kind == "mode" else 0o644)
    if bad_kind == "parent_link":
        alias = source / "alias"
        alias.symlink_to(source, target_is_directory=True)
        with pytest.raises(OSError):
            preflight.open_checked(alias / "module.py", owners)
    else:
        with pytest.raises(preflight.PreflightError):
            preflight.inspect_tree(source, roots, owners)


def test_uv_hardlink_inode_must_still_be_nonwritable_by_other(trust_tree):
    source, _, roots, owners = trust_tree
    module = source / "module.py"
    module.write_text("pass")
    module.chmod(0o644)
    os.link(module, source / "uv-cache-alias.py")
    assert preflight.inspect_tree(source, roots, owners)["entries"] == 2
    module.chmod(0o666)
    with pytest.raises(preflight.PreflightError, match="writable_code_path"):
        preflight.inspect_tree(source, roots, owners)


def test_startup_hooks_cannot_add_unapproved_import_roots(trust_tree):
    source, _, roots, owners = trust_tree
    hook = source / "_virtualenv.pth"
    hook.write_text("import _virtualenv")
    hook.chmod(0o644)
    preflight.validate_startup_file(hook, source, roots, owners)
    hook.write_text("/var/lib/station/zones/other/home")
    with pytest.raises(preflight.PreflightError, match="unreviewed_python_startup"):
        preflight.validate_startup_file(hook, source, roots, owners)


@pytest.mark.parametrize("target", ["/var/lib/station/zones/other/home", "EXCLUDED"])
def test_editable_finder_mappings_are_confined(trust_tree, target):
    source, _, roots, owners = trust_tree
    finder = "__editable___hermes_agent_0_21_0_finder"
    hook = source / "__editable__.hermes_agent-0.21.0.pth"
    hook.write_text(f"import {finder}; {finder}.install()")
    hook.chmod(0o644)
    module = source / (finder + ".py")
    module.write_text(f"MAPPING: dict = {{'agent': {str(source / 'agent')!r}}}\nNAMESPACES: dict = {{}}\n")
    module.chmod(0o644)
    preflight.validate_startup_file(hook, source, roots, owners)
    target = str(source / ".git/evil") if target == "EXCLUDED" else target
    module.write_text(f"MAPPING: dict = {{'agent': {target!r}}}\nNAMESPACES: dict = {{}}\n")
    with pytest.raises(preflight.PreflightError, match="editable_mapping_escape"):
        preflight.validate_startup_file(hook, source, roots, owners)


def make_known_modes(source, python):
    paths = []
    for relative, kind, before, after in preflight.KNOWN_MODE_REPAIRS:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "directory":
            target.mkdir()
        else:
            target.write_bytes(b"")
        target.chmod(before)
        paths.append((target, after))
    lock = python / ".lock"
    lock.write_bytes(b"")
    lock.chmod(0o666)
    paths.append((lock, 0o600))
    return paths


def test_known_mode_repair_is_exact_and_idempotent(trust_tree):
    source, python, _, owners = trust_tree
    expected = make_known_modes(source, python)
    unrelated = source / "unrelated.py"
    unrelated.write_text("pass")
    unrelated.chmod(0o664)
    changed = preflight.repair_known_modes(source, python, owners)
    assert len(changed) == 6
    assert all(stat.S_IMODE(path.stat().st_mode) == mode for path, mode in expected)
    assert stat.S_IMODE(unrelated.stat().st_mode) == 0o664
    assert preflight.repair_known_modes(source, python, owners) == []


@pytest.mark.parametrize("bad", ["contents", "link", "hardlink", "mode"])
def test_known_mode_repair_refuses_unreviewed_lock(trust_tree, bad):
    source, python, _, owners = trust_tree
    make_known_modes(source, python)
    lock = source / "venv/.lock"
    if bad == "contents":
        lock.write_text("not the empty reviewed uv lock")
    elif bad == "link":
        lock.unlink()
        lock.symlink_to(python / ".lock")
    elif bad == "hardlink":
        os.link(lock, source / "alias")
    else:
        lock.chmod(0o777)
    with pytest.raises(preflight.PreflightError):
        preflight.repair_known_modes(source, python, owners)
