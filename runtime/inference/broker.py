#!/usr/bin/python3
"""Source-owned, loopback-only inference transport; not a Hermes agent gateway.

HTTP authenticates possession of a Zone capability, not kernel peer credentials.
All roles in a Zone share its Unix authority. No source credential, source agent,
session, account tool, or filesystem API is made available to the target.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import http.client
import json
import logging
import os
from pathlib import Path
import pwd
import re
import selectors
import socket
import socketserver
import ssl
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


CONFIG_PATH = Path("/opt/station/inference/config.json")
SOURCE_HOME = "/home/agk-station"
SOURCE_HERMES_HOME = SOURCE_HOME + "/.hermes"
HERMES_CURRENT = Path("/opt/station/tools/hermes/current")
HERMES_PIN = "29112bef099274229cadff79cdff7bf7b99c4b77"
UPSTREAM_HOST = "chatgpt.com"
UPSTREAM_BASE = "https://chatgpt.com/backend-api/codex"
UPSTREAM_PATH = "/backend-api/codex/responses"
MAX_REQUEST = 4 * 1024 * 1024
MAX_STREAM = 64 * 1024 * 1024
MAX_CONFIG = 256 * 1024
MAX_WORKERS = 8
CLIENT_TIMEOUT = 15
UPSTREAM_TIMEOUT = 60
STREAM_DEADLINE = 600
SOURCE_TIMEOUT = 45
CHUNK_SIZE = 16 * 1024
MAX_EVENT = 1024 * 1024
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]{0,62}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")


class BrokerError(Exception):
    def __init__(self, code: str, status: int = 503):
        self.code, self.status = code, status
        super().__init__(code)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(raw: bytes):
    return json.loads(raw, object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def _open_directory(path: Path, owners: tuple[int, ...]) -> int:
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            if st.st_uid not in owners or stat.S_IMODE(st.st_mode) & 0o022:
                raise BrokerError("unsafe_source_path")
        return fd
    except BaseException:
        os.close(fd)
        raise


def protected_read(path: Path, *, owner: int = 0, mode: int = 0o640,
                   limit: int = MAX_CONFIG) -> bytes:
    parent = _open_directory(path.parent, (0, owner))
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != owner or st.st_nlink != 1
                    or stat.S_IMODE(st.st_mode) != mode or st.st_size > limit):
                raise BrokerError("unsafe_config")
            raw = os.read(fd, limit + 1)
            if len(raw) > limit:
                raise BrokerError("unsafe_config")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def validate_config(value: object, *, account_lookup=pwd.getpwuid) -> dict:
    if (not isinstance(value, dict) or set(value) != {"schema_version", "port", "source", "grants"}
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or type(value.get("port")) is not int or not 1024 <= value["port"] <= 65535
            or value.get("source") != {"operator": "agk-station", "hermes_home": SOURCE_HERMES_HOME}
            or not isinstance(value.get("grants"), list) or len(value["grants"]) > 256):
        raise BrokerError("invalid_config")
    zones, uids, hashes = set(), set(), set()
    for grant in value["grants"]:
        if (not isinstance(grant, dict) or set(grant) != {"zone_id", "uid", "token_sha256"}
                or not isinstance(grant["zone_id"], str) or not IDENTIFIER.fullmatch(grant["zone_id"])
                or type(grant["uid"]) is not int or not 0 < grant["uid"] < 2**31
                or not isinstance(grant["token_sha256"], str) or not HEX.fullmatch(grant["token_sha256"])
                or grant["zone_id"] in zones or grant["uid"] in uids or grant["token_sha256"] in hashes):
            raise BrokerError("invalid_grant")
        try:
            account = account_lookup(grant["uid"])
        except KeyError:
            raise BrokerError("invalid_grant_identity") from None
        if account.pw_dir != f"/var/lib/station/zones/{grant['zone_id']}/home":
            raise BrokerError("invalid_grant_identity")
        zones.add(grant["zone_id"])
        uids.add(grant["uid"])
        hashes.add(grant["token_sha256"])
    return value


def load_config() -> dict:
    try:
        return validate_config(decode_json(protected_read(CONFIG_PATH)))
    except (OSError, ValueError, RecursionError, TypeError):
        raise BrokerError("invalid_config") from None


def source_identity():
    uid = os.geteuid()
    account = pwd.getpwnam("agk-station")
    if (uid == 0 or uid != os.getuid() or uid != account.pw_uid
            or account.pw_dir != SOURCE_HOME or os.environ.get("HOME") != SOURCE_HOME
            or os.environ.get("HERMES_HOME") != SOURCE_HERMES_HOME):
        raise BrokerError("source_identity_mismatch")
    return account


def validate_source_tree(root: Path, uid: int) -> None:
    """Refuse target-writable Python source/cache before importing native code.

    Dependency/interpreter trees are separately checked by privileged activation
    before Python is launched. Node and Git metadata are not Python import roots.
    The existing source operator retains authority to modify its own source.
    """
    count = 0
    def walk(fd, depth):
        nonlocal count
        if depth > 100:
            raise BrokerError("unsafe_hermes_source")
        for name in os.listdir(fd):
            if name == 'node_modules' or (depth == 0 and name in {".git", "venv", ".venv"}):
                continue
            count += 1
            if count > 100000:
                raise BrokerError("unsafe_hermes_source")
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if st.st_uid not in (0, uid) or stat.S_IMODE(st.st_mode) & 0o022:
                raise BrokerError("unsafe_hermes_source")
            if stat.S_ISDIR(st.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino):
                        raise BrokerError("unsafe_hermes_source")
                    walk(child, depth + 1)
                finally:
                    os.close(child)
            elif not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise BrokerError("unsafe_hermes_source")
    fd = _open_directory(root, (0, uid))
    try:
        walk(fd, 0)
    finally:
        os.close(fd)


def trusted_hermes_path(uid: int) -> Path:
    parent = _open_directory(HERMES_CURRENT.parent, (0, uid))
    try:
        st = os.stat(HERMES_CURRENT.name, dir_fd=parent, follow_symlinks=False)
        if st.st_uid not in (0, uid):
            raise BrokerError("unsafe_hermes_source")
        resolved = HERMES_CURRENT.resolve(strict=True)
        if not resolved.is_relative_to(HERMES_CURRENT.parent):
            raise BrokerError("unsafe_hermes_source")
        checked = _open_directory(resolved, (0, uid))
        os.close(checked)
    finally:
        os.close(parent)
    # Source code can be owned by its executing account, never by a target Zone.
    # This does not claim immutability against the source operator itself.
    result = subprocess.run(["/usr/bin/git", "-c", "core.fsmonitor=false", "-C", str(resolved),
                             "rev-parse", "HEAD"], check=False, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=10,
                            env={"HOME": SOURCE_HOME, "PATH": "/usr/bin:/bin",
                                 "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
    if result.returncode or result.stdout.strip() != HERMES_PIN.encode("ascii"):
        raise BrokerError("hermes_pin_mismatch")
    validate_source_tree(resolved, uid)
    return resolved


def resolve_source_native() -> dict:
    account = source_identity()
    source = trusted_hermes_path(account.pw_uid)
    sys.path.insert(0, str(source))
    # Native config/auth resolution is source-owned and may rotate source OAuth.
    # It never executes a target provider/key command or imports target code.
    logging.disable(logging.CRITICAL)
    with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        from hermes_cli.config import load_config_readonly
        from hermes_cli.runtime_provider import resolve_runtime_provider
        from agent.codex_headers import codex_cloudflare_headers

        config = load_config_readonly()
        model = config.get("model") if isinstance(config, dict) else None
        if (not isinstance(model, dict) or model.get("provider") != "openai-codex"
                or not isinstance(model.get("default"), str) or not MODEL.fullmatch(model["default"])):
            raise BrokerError("source_provider_not_supported")
        runtime = resolve_runtime_provider(requested="openai-codex", target_model=model["default"])
        token = runtime.get("api_key")
        if (runtime.get("provider") != "openai-codex" or runtime.get("api_mode") != "codex_responses"
                or runtime.get("base_url", "").rstrip("/") != UPSTREAM_BASE
                or not isinstance(token, str) or not token or len(token) > 32768
                or any(ord(char) < 33 or ord(char) > 126 for char in token)):
            raise BrokerError("source_credentials_unavailable")
        identity = codex_cloudflare_headers(token, base_url=UPSTREAM_BASE)
        headers = {key: value for key, value in identity.items()
                   if key.lower() in {"user-agent", "originator", "chatgpt-account-id"}
                   and isinstance(value, str) and len(value) < 1024
                   and all(32 <= ord(char) < 127 for char in value)}
        headers.update({"Authorization": "Bearer " + token, "Content-Type": "application/json",
                        "Accept": "text/event-stream", "Accept-Encoding": "identity"})
        return {"model": model["default"], "headers": headers}


class NativeSource:
    """Bounded, quiet helper; secrets travel only over an inherited private pipe."""

    def __init__(self):
        self.lock = threading.Lock()

    def resolve(self) -> dict:
        if not self.lock.acquire(timeout=SOURCE_TIMEOUT):
            raise BrokerError("source_busy", 503)
        read_fd, write_fd = os.pipe()
        child = None
        try:
            child = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                                      "--source-fd", str(write_fd)], pass_fds=(write_fd,),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, cwd=SOURCE_HOME,
                                     env={"HOME": SOURCE_HOME, "HERMES_HOME": SOURCE_HERMES_HOME,
                                          "USER": "agk-station", "LOGNAME": "agk-station",
                                          "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
            os.close(write_fd)
            write_fd = -1
            raw = bytearray()
            deadline = time.monotonic() + SOURCE_TIMEOUT
            with selectors.DefaultSelector() as selector:
                selector.register(read_fd, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise BrokerError("source_timeout")
                    chunk = os.read(read_fd, 8192)
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise BrokerError("source_credentials_unavailable")
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
            if child.returncode:
                # Codes are a closed set; never return native exception text.
                errors = {20: "source_provider_not_supported", 21: "hermes_pin_mismatch"}
                raise BrokerError(errors.get(child.returncode, "source_credentials_unavailable"))
            result = decode_json(bytes(raw))
            if (not isinstance(result, dict) or set(result) != {"model", "headers"}
                    or not isinstance(result["model"], str) or not MODEL.fullmatch(result["model"])
                    or not isinstance(result["headers"], dict)):
                raise BrokerError("source_credentials_unavailable")
            return result
        except (OSError, ValueError, subprocess.SubprocessError):
            raise BrokerError("source_credentials_unavailable") from None
        finally:
            os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()
            self.lock.release()


def normalize_request(value: object, model: str, grant: dict) -> bytes:
    allowed = {"model", "instructions", "input", "tools", "store", "stream", "reasoning",
               "include", "max_output_tokens", "temperature", "top_p", "tool_choice",
               "parallel_tool_calls", "prompt_cache_key", "prompt_cache_retention",
               "service_tier", "context_management", "text", "truncation"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise BrokerError("unsupported_request_fields", 400)
    if value.get("model") not in ("hermes-default", model):
        raise BrokerError("model_not_selected", 400)
    if not isinstance(value.get("input"), (str, list)):
        raise BrokerError("invalid_input", 400)
    if isinstance(value["input"], list):
        for item in value["input"]:
            if not isinstance(item, dict) or item.get("type", "message") not in {
                    "message", "function_call", "function_call_output", "reasoning"}:
                raise BrokerError("account_state_not_supported", 400)
            if item.get("type", "message") == "message":
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if (not isinstance(part, dict) or part.get("type") not in {
                                "input_text", "output_text", "input_image", "refusal"}
                                or "file_id" in part):
                            raise BrokerError("account_state_not_supported", 400)
                elif not isinstance(content, str):
                    raise BrokerError("invalid_input", 400)
            if item.get("type") == "function_call_output" and not isinstance(item.get("output"), str):
                raise BrokerError("invalid_tool_output", 400)
    tools = value.get("tools", [])
    if (not isinstance(tools, list) or len(tools) > 256
            or any(not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools)):
        raise BrokerError("hosted_tools_not_supported", 400)
    choice = value.get("tool_choice", "auto")
    if not (choice in ("auto", "none", "required") if isinstance(choice, str)
            else isinstance(choice, dict) and choice.get("type") == "function"):
        raise BrokerError("hosted_tools_not_supported", 400)
    if "include" in value and (not isinstance(value["include"], list)
                              or any(item != "reasoning.encrypted_content" for item in value["include"])):
        raise BrokerError("account_state_not_supported", 400)
    result = dict(value)
    result.update(model=model, store=False, stream=True)
    result.pop("max_output_tokens", None)
    result.pop("prompt_cache_retention", None)
    if "prompt_cache_key" in result:
        if not isinstance(result["prompt_cache_key"], str) or len(result["prompt_cache_key"]) > 1024:
            raise BrokerError("invalid_cache_key", 400)
        result["prompt_cache_key"] = hashlib.sha256(
            (grant["zone_id"] + ":" + result["prompt_cache_key"]).encode()).hexdigest()
    return json.dumps(result, separators=(",", ":"), allow_nan=False).encode()


def open_upstream(payload: bytes, headers: dict):
    """No environment proxies or redirects; the upstream origin/path are constants."""
    connection = http.client.HTTPSConnection(UPSTREAM_HOST, 443, timeout=UPSTREAM_TIMEOUT,
                                              context=ssl.create_default_context())
    try:
        connection.request("POST", UPSTREAM_PATH, payload, headers)
        return connection, connection.getresponse()
    except BaseException:
        connection.close()
        raise


def safe_event(frame: bytes) -> bytes:
    """Keep successful inference verbatim; redact provider diagnostics inside SSE."""
    lines = frame.replace(b"\r\n", b"\n").split(b"\n")
    if any(line and not line.startswith((b':', b'event:', b'data:', b'id:', b'retry:')) for line in lines):
        raise BrokerError('invalid_upstream_event', 502)
    events = [line[6:].strip() for line in lines if line.startswith(b"event:")]
    event_kind = events[-1].decode("ascii", errors="replace") if events else ""
    data = b"\n".join(line[5:].lstrip(b" ") for line in lines if line.startswith(b"data:"))
    if not data or data == b"[DONE]":
        if event_kind in ("error", "response.failed", "response.incomplete"):
            return b'event: error\ndata: {"type":"error","error":{"code":"upstream_inference_failed","message":"upstream_inference_failed"}}\n\n'
        return frame
    try:
        value = decode_json(data)
    except (ValueError, RecursionError):
        raise BrokerError("invalid_upstream_event", 502) from None
    if not isinstance(value, dict):
        raise BrokerError("invalid_upstream_event", 502)
    kind = value.get("type", "")
    failure_kinds = ("error", "response.failed", "response.incomplete")
    envelope = value.get("response")
    response_failed = isinstance(envelope, dict) and (
        envelope.get("error") is not None or envelope.get("status") in ("failed", "incomplete"))
    if kind in failure_kinds or event_kind in failure_kinds or value.get("error") is not None or response_failed:
        kind = kind if kind in failure_kinds else event_kind if event_kind in failure_kinds else "error"
        error = {"code": "upstream_inference_failed", "message": "upstream_inference_failed"}
        value = {"type": kind, "error": error} if kind == "error" else {
            "type": kind, "response": {"status": kind.split(".")[1], "error": error}}
        return b"event: " + kind.encode("ascii") + b"\ndata: " + json.dumps(value).encode() + b"\n\n"
    return frame


def stream_events(response, *, deadline: float):
    """Bounded event framing, never a complete response buffer."""
    pending, count = bytearray(), 0
    while time.monotonic() < deadline:
        chunk = response.read1(CHUNK_SIZE)
        if not chunk:
            if pending:
                raise BrokerError("incomplete_upstream_event", 502)
            return
        count += len(chunk)
        if count > MAX_STREAM:
            raise BrokerError("upstream_stream_limit", 502)
        pending.extend(chunk)
        while True:
            candidates = [(pending.find(end), end) for end in (b"\n\n", b"\r\n\r\n")]
            candidates = [(index, end) for index, end in candidates if index >= 0]
            if not candidates:
                break
            index, end = min(candidates, key=lambda item: item[0])
            if index + len(end) > MAX_EVENT:
                raise BrokerError("upstream_event_limit", 502)
            frame = bytes(pending[:index + len(end)])
            del pending[:index + len(end)]
            yield safe_event(frame)
        if len(pending) > MAX_EVENT:
            raise BrokerError("upstream_event_limit", 502)
    raise BrokerError("upstream_stream_timeout", 504)


class InferenceServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = MAX_WORKERS

    def __init__(self, port: int, *, config_loader=load_config, source=None, upstream=open_upstream):
        self.config_loader = config_loader
        self.source = source if source is not None else NativeSource()
        self.upstream = upstream
        self.slots = threading.BoundedSemaphore(MAX_WORKERS)
        super().__init__(("127.0.0.1", port), InferenceHandler)

    def process_request(self, request, client_address):
        request.settimeout(CLIENT_TIMEOUT)
        if not self.slots.acquire(blocking=False):
            with contextlib.suppress(OSError):
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Base implementation prints tracebacks and may include request material.
        pass


class InferenceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "StationInference"
    sys_version = ""

    def handle(self):
        # Socket inactivity limits alone do not bound a slowloris header stream.
        def expire_headers():
            with contextlib.suppress(OSError):
                self.connection.shutdown(socket.SHUT_RDWR)
        self._header_timer = threading.Timer(CLIENT_TIMEOUT, expire_headers)
        self._header_timer.daemon = True
        self._header_timer.start()
        try:
            super().handle()
        finally:
            self._header_timer.cancel()

    def parse_request(self):
        try:
            return super().parse_request()
        finally:
            self._header_timer.cancel()

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.error("invalid_http_request", code)

    def error(self, code: str, status: int):
        self.reply(status, {"error": {"code": code, "message": code}})

    def reply(self, status: int, value: dict):
        raw = json.dumps(value, separators=(",", ":")).encode()
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _grant(self, config: dict) -> dict:
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1 or not values[0].startswith("Bearer "):
            raise BrokerError("invalid_capability", 401)
        token = values[0][7:]
        if not HEX.fullmatch(token):
            raise BrokerError("invalid_capability", 401)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        for grant in config["grants"]:
            if hmac.compare_digest(digest, grant["token_sha256"]):
                return grant
        raise BrokerError("invalid_capability", 401)

    def _request(self):
        host = self.headers.get_all("Host", [])
        port = self.server.server_port
        if (self.client_address[0] != "127.0.0.1" or len(host) != 1
                or host[0] not in (f"127.0.0.1:{port}", f"localhost:{port}")
                or self.headers.get("Origin") is not None):
            raise BrokerError("local_client_required", 403)
        if self.command == "GET" and self.path == "/health":
            self.reply(200, {"status": "listening", "provider_readiness": "not_checked"})
            return
        config = self.server.config_loader()  # grants/revocation re-read for every request
        grant = self._grant(config)  # authorize before body reads or native/upstream work
        if self.command == "GET" and self.path in ("/models", "/v1/models"):
            source = self.server.source.resolve()
            self.reply(200, {"object": "list", "data": [
                {"id": name, "object": "model", "owned_by": "station-inference"}
                for name in dict.fromkeys(("hermes-default", source["model"]))]})
            return
        if self.command != "POST" or self.path not in ("/responses", "/v1/responses"):
            raise BrokerError("route_not_supported", 404)
        lengths = self.headers.get_all("Content-Length", [])
        if (self.headers.get("Transfer-Encoding") is not None
                or self.headers.get("Content-Encoding") is not None
                or self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json"
                or len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,8}", lengths[0])):
            raise BrokerError("invalid_body_framing", 400)
        length = int(lengths[0])
        if not 0 < length <= MAX_REQUEST:
            raise BrokerError("request_too_large", 413)
        deadline, body = time.monotonic() + CLIENT_TIMEOUT, bytearray()
        while len(body) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrokerError("request_timeout", 408)
            self.connection.settimeout(remaining)
            chunk = self.rfile.read1(min(CHUNK_SIZE, length - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        self.connection.settimeout(CLIENT_TIMEOUT)
        raw = bytes(body)
        if len(raw) != length:
            raise BrokerError("incomplete_request", 400)
        try:
            value = decode_json(raw)
        except (ValueError, RecursionError):
            raise BrokerError("invalid_json", 400) from None
        source = self.server.source.resolve()
        payload = normalize_request(value, source["model"], grant)
        # Source refresh can wait in a bounded queue. Recheck a revocation before
        # any paid upstream request; an already-started stream is not recalled.
        current_grant = self._grant(self.server.config_loader())
        if current_grant != grant:
            raise BrokerError("invalid_capability", 401)
        connection, response = self.server.upstream(payload, source["headers"])
        try:
            if response.status != 200:
                status = response.status if response.status in (400, 401, 403, 429) else 502
                raise BrokerError("upstream_request_failed", status)
            # The pinned Codex origin can return valid SSE without Content-Type.
            # An absent header is not a different protocol: frames still undergo
            # bounded SSE/JSON validation; an explicit other MIME type is refused.
            if (response.getheader("Content-Type", "").split(";", 1)[0].strip() not in ('', "text/event-stream")
                    or response.getheader("Content-Encoding", "identity") != "identity"):
                raise BrokerError("invalid_upstream_response", 502)
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self._stream_started = True
            for frame in stream_events(response, deadline=time.monotonic() + STREAM_DEADLINE):
                self.wfile.write(frame)
                self.wfile.flush()
            # No retry after output: duplicate paid inference/tool events are unsafe.
        finally:
            response.close()
            connection.close()

    def _dispatch(self):
        self._stream_started = False
        try:
            self._request()
        except BrokerError as exc:
            if not self._stream_started:
                with contextlib.suppress(OSError):
                    self.error(exc.code, exc.status)
        except (OSError, ValueError, http.client.HTTPException, TypeError, KeyError):
            if not self._stream_started:
                with contextlib.suppress(OSError):
                    self.error("inference_temporarily_unavailable", 502)
        finally:
            self.close_connection = True

    do_GET = _dispatch
    do_POST = _dispatch
    do_PUT = _dispatch
    do_DELETE = _dispatch
    do_PATCH = _dispatch
    do_OPTIONS = _dispatch
    do_HEAD = _dispatch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--source-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        source_identity()
        if args.source_fd is not None:
            if args.source_fd < 3 or not stat.S_ISFIFO(os.fstat(args.source_fd).st_mode):
                raise BrokerError("invalid_source_pipe")
            try:
                raw = json.dumps(resolve_source_native(), separators=(",", ":")).encode()
                if len(raw) > 65536:
                    raise BrokerError("source_credentials_unavailable")
                with os.fdopen(args.source_fd, "wb") as pipe:
                    pipe.write(raw)
                return 0
            except BrokerError as exc:
                return {"source_provider_not_supported": 20, "hermes_pin_mismatch": 21}.get(exc.code, 1)
        if args.config != str(CONFIG_PATH):
            raise BrokerError("fixed_config_required")
        config = load_config()
        with InferenceServer(config["port"]) as server:
            server.serve_forever(poll_interval=0.25)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        # No auth errors, request bodies, identities, or tracebacks in journal.
        if args.source_fd is None:
            print("Station inference broker unavailable; inspect its scoped configuration", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
