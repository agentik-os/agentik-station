"""Adversarial tests for the governed Hermes web adapters (no network/LLM calls)."""

from __future__ import annotations

import asyncio
import importlib
import io
import json
import socket
import subprocess
import sys
import types
from email.message import Message
from pathlib import Path
from urllib.parse import urlsplit

import pytest


PLUGIN = Path(__file__).resolve().parents[1] / "hermes/plugins/agentik_os"


@pytest.fixture
def web(monkeypatch):
    package = types.ModuleType("station_web_test")
    package.__path__ = [str(PLUGIN)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    registry = types.ModuleType("tools.registry")
    registry.tool_result = json.dumps
    registry.tool_error = lambda error: json.dumps({"error": error})
    monkeypatch.setitem(sys.modules, "tools.registry", registry)
    loaded = {}
    for name in ("web_fetch", "web_runtime", "scrapegraph_tool", "web_plugin"):
        key = f"{package.__name__}.{name}"
        monkeypatch.delitem(sys.modules, key, raising=False)
        loaded[name] = importlib.import_module(key)
        monkeypatch.setitem(sys.modules, name, loaded[name])
    key = f"{package.__name__}.scrapegraph_runner"
    monkeypatch.delitem(sys.modules, key, raising=False)
    loaded["runner"] = importlib.import_module(key)
    return types.SimpleNamespace(**loaded)


def addresses(ip="93.184.216.34"):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "::1", "::ffff:127.0.0.1", "224.0.0.1", "fc00::1", "0.0.0.0"])
def test_nonpublic_dns_is_rejected(web, monkeypatch, ip):
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", lambda *a, **k: addresses(ip))
    with pytest.raises(ValueError, match="private or reserved"):
        web.web_fetch.public_target("https://example.com/")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:secret@example.com", "https://localhost/", "http://host.internal/", "https://example.com:8443/", "https://example.com/\r\nX:yes", "https://example.com\\@localhost/", "https:///missing-host"])
def test_invalid_url_is_rejected_before_dns(web, monkeypatch, url):
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS should not run"))
    with pytest.raises(ValueError):
        web.web_fetch.public_target(url)


def test_mixed_public_private_dns_is_rejected(web, monkeypatch):
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", lambda *a, **k: addresses() + addresses("10.1.2.3"))
    with pytest.raises(ValueError):
        web.web_fetch.public_target("https://example.com")


class Response:
    def __init__(self, status=200, body=b"<h1>fixture</h1>", **headers):
        self.status, self.body = status, body
        self.headers = Message()
        self.headers["Content-Type"] = headers.pop("Content-Type", "text/html; charset=utf-8")
        for key, value in headers.items():
            self.headers[key] = value

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, size):
        return self.body[:size]


class Connection:
    def __init__(self, response):
        self.response, self.closed = response, False

    def request(self, *args, **kwargs):
        self.requested = (args, kwargs)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def test_redirect_to_private_host_is_blocked_before_connect(web, monkeypatch):
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", lambda host, *a, **k: addresses("10.0.0.1") if host == "secret.example" else addresses())
    first = Connection(Response(302, Location="http://secret.example/metadata"))
    connected = []
    def connect(*args):
        connected.append(args)
        return first
    monkeypatch.setattr(web.web_fetch, "_connection", connect)
    with pytest.raises(ValueError, match="private or reserved"):
        web.web_fetch.fetch_html("https://example.com/start")
    assert len(connected) == 1
    assert first.closed


def test_public_redirect_is_revalidated_and_relative_url_resolved(web, monkeypatch):
    resolved = []
    def resolve(host, *a, **k):
        resolved.append(host)
        return addresses()
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", resolve)
    responses = [Connection(Response(302, Location="/next")), Connection(Response())]
    monkeypatch.setattr(web.web_fetch, "_connection", lambda *a: responses.pop(0))
    assert web.web_fetch.fetch_html("https://example.com/start") == ("<h1>fixture</h1>", "https://example.com/next")
    assert resolved == ["example.com", "example.com"]


def test_connection_uses_validated_sockaddr_without_second_dns(web, monkeypatch):
    class Sock:
        def settimeout(self, value):
            assert value == 15
        def connect(self, address):
            self.address = address
    sock = Sock()
    monkeypatch.setattr(web.web_fetch.socket, "socket", lambda *args: sock)
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS rebinding opportunity"))
    conn = web.web_fetch._connection(urlsplit("http://example.com"), "example.com", 80, addresses())
    assert conn.sock is sock
    assert sock.address == ("93.184.216.34", 443)


@pytest.mark.parametrize("response,error", [
    (Response(200, b"x" * (2 * 1024 * 1024 + 1)), "2 MiB"),
    (Response(200, **{"Content-Type": "application/octet-stream"}), "HTML or plain text"),
    (Response(200, **{"Content-Encoding": "gzip"}), "compressed"),
    (Response(403), "unsuccessful"),
])
def test_response_limits(web, monkeypatch, response, error):
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", lambda *a, **k: addresses())
    conn = Connection(response)
    monkeypatch.setattr(web.web_fetch, "_connection", lambda *a: conn)
    with pytest.raises(ValueError, match=error):
        web.web_fetch.fetch_html("https://example.com/")
    assert conn.closed


def test_worker_accepts_normal_venv_python_symlink(web, monkeypatch, tmp_path):
    runtime = tmp_path / "crawl4ai"
    (runtime / "venv/bin").mkdir(parents=True)
    (runtime / "venv/bin/python").symlink_to(sys.executable)
    monkeypatch.setattr(web.scrapegraph_tool, "runtime_root", lambda component: runtime)
    assert web.scrapegraph_tool._worker("crawl4ai") == runtime / "venv/bin/python"


@pytest.mark.parametrize("component", ["scrapegraphai", "crawl4ai"])
def test_worker_environment_does_not_inherit_other_credentials(web, monkeypatch, tmp_path, component):
    tool = web.scrapegraph_tool
    monkeypatch.setattr(tool.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(tool, "_worker", lambda component: Path(sys.executable))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "selected-key")
    monkeypatch.setenv("HTTP_PROXY", "http://private-proxy")
    captured = {}
    class Process:
        returncode = 0
        def poll(self):
            return self.returncode
        def __init__(self, argv, **kwargs):
            captured.update(argv=argv, **kwargs)
        def communicate(self, payload, timeout):
            assert timeout == 180
            captured["payload"] = json.loads(payload)
            captured["stdout"].write(b'{"success":true,"data":"fixture"}')
    monkeypatch.setattr(tool.subprocess, "Popen", Process)
    assert tool._run_worker(component, {"source": "https://example.com"})["success"]
    env = captured["env"]
    assert not {"DISCORD_BOT_TOKEN", "GITHUB_TOKEN", "HTTP_PROXY", "OPENAI_API_KEY"} & env.keys()
    assert env.get("SCRAPEGRAPHAI_OPENAI_API_KEY") == ("selected-key" if component == "scrapegraphai" else None)
    assert "selected-key" not in str(captured["argv"])
    assert captured["payload"]["component"] == component
    assert captured["start_new_session"] is True
    assert not Path(captured["cwd"]).exists()


def test_timeout_kills_worker_group_and_removes_scratch(web, monkeypatch, tmp_path):
    tool = web.scrapegraph_tool
    monkeypatch.setattr(tool.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(tool, "_worker", lambda component: Path(sys.executable))
    monkeypatch.setenv("HOME", str(tmp_path))
    killed = []
    class Process:
        pid = 123456
        def poll(self):
            return None
        def __init__(self, *args, **kwargs):
            pass
        def communicate(self, *args, **kwargs):
            raise subprocess.TimeoutExpired("worker", 180)
        def wait(self):
            return -9
    monkeypatch.setattr(tool.subprocess, "Popen", Process)
    monkeypatch.setattr(tool.os, "killpg", lambda *args: killed.append(args))
    with pytest.raises(ValueError, match="180 seconds"):
        tool._run_worker("crawl4ai", {"source": "https://example.com"})
    assert killed == [(123456, tool.signal.SIGKILL)]
    assert not list((tmp_path / ".cache/station-web").iterdir())


def test_root_unknown_arguments_and_unsupported_model_fail_closed(web, monkeypatch):
    tool = web.scrapegraph_tool
    monkeypatch.setattr(tool.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="owning Zone"):
        tool._run_worker("crawl4ai", {})
    assert "error" in json.loads(tool.handle_crawl4ai({"source": "https://example.com", "command": "anything"}))
    monkeypatch.setattr(tool, "public_target", lambda source: None)
    assert "error" in json.loads(tool.handle_scrapegraph({"source": "https://example.com", "prompt": "fixture", "model": "local/anything"}))


def test_registration_uses_native_function_schemas_and_readiness_probes(web):
    tools = []
    ctx = types.SimpleNamespace(register_tool=lambda **kwargs: tools.append(kwargs))
    web.web_plugin.register(ctx)
    assert {entry["name"] for entry in tools} == {"station_crawl4ai", "station_scrapegraph"}
    for entry in tools:
        assert entry["schema"]["name"] == entry["name"]
        assert entry["schema"]["parameters"]["additionalProperties"] is False
        assert entry["toolset"] == "web"
        assert callable(entry["check_fn"])


def test_scrapegraph_receives_prefetched_html_not_a_navigable_url(web, monkeypatch):
    monkeypatch.setattr(web.runner.importlib.metadata, "version", lambda _: "2.2.2")
    monkeypatch.setattr(web.runner, "fetch_html", lambda source: ("https://private.example/ is untrusted page text", source))
    monkeypatch.setenv("SCRAPEGRAPHAI_OPENAI_API_KEY", "fixture-key")
    captured = {}
    class Graph:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        def run(self):
            return {"title": "fixture"}
    graphs = types.ModuleType("scrapegraphai.graphs")
    graphs.SmartScraperGraph = Graph
    monkeypatch.setitem(sys.modules, "scrapegraphai.graphs", graphs)
    assert web.runner.extract({"component": "scrapegraphai", "source": "https://example.com", "prompt": "title", "model": "openai/gpt-4o-mini"})["data"] == {"title": "fixture"}
    assert captured["source"].startswith("<html>")
    assert captured["config"]["llm"]["api_key"] == "fixture-key"


def test_provider_exception_does_not_leak_through_worker_output(web, monkeypatch, capsys):
    monkeypatch.setattr(web.runner.sys, "stdin", io.StringIO('{}'))
    def fail(request):
        print("provider-secret")
        raise RuntimeError("provider-secret")
    monkeypatch.setattr(web.runner, "extract", fail)
    assert web.runner.main() == 1
    output = capsys.readouterr()
    assert "provider-secret" not in output.out + output.err
    assert json.loads(output.out)["success"] is False


def test_real_crawl4ai_raw_html_when_dependency_is_installed(web):
    pytest.importorskip("crawl4ai")
    markdown = asyncio.run(web.runner.crawl_html("<h1>Station fixture</h1><p>Offline extraction works.</p>", "https://example.com"))
    assert "# Station fixture" in markdown
    assert "Offline extraction works." in markdown


def test_hermes_parent_never_resolves_dns_outside_worker_deadline(web, monkeypatch):
    monkeypatch.setattr(web.web_fetch.socket, "getaddrinfo", lambda *a, **kw: pytest.fail("DNS belongs in deadline-controlled worker"))
    monkeypatch.setattr(web.scrapegraph_tool, "_run_worker", lambda *a: {"success": True, "markdown": "fixture"})
    assert json.loads(web.scrapegraph_tool.handle_crawl4ai({"source": "https://example.com"}))["success"] is True


def test_real_scrapegraph_graph_with_offline_model(web, monkeypatch):
    graphs = pytest.importorskip("scrapegraphai.graphs")
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    real_graph = graphs.SmartScraperGraph
    def offline_graph(**kwargs):
        kwargs["config"]["llm"] = {"model_instance": FakeListChatModel(responses=['{"title":"Station fixture"}']), "model_tokens": 8192}
        return real_graph(**kwargs)
    monkeypatch.setattr(graphs, "SmartScraperGraph", offline_graph)
    monkeypatch.setattr(web.runner, "fetch_html", lambda _: ("<h1>Station fixture</h1>", "https://example.com"))
    monkeypatch.setenv("SCRAPEGRAPHAI_TELEMETRY_ENABLED", "false")
    monkeypatch.setenv("SCRAPEGRAPHAI_OPENAI_API_KEY", "synthetic-not-a-key")
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **kw: pytest.fail("No network permitted in offline graph test"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("Prewarm public tokenizer assets before the offline test"))
    result = web.runner.extract({"component": "scrapegraphai", "source": "https://example.com", "prompt": "Return the title", "model": "openai/fixture"})
    assert result == {"success": True, "data": {"title": "Station fixture"}}
