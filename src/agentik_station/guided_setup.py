from __future__ import annotations

import fcntl
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import stat
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlsplit

from .errors import SecurityError, ValidationError
from .identifiers import validate_identifier


_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{40,96}$")
_PURPOSES = {"station-secret", "hermes-credentials", "composio-oauth", "cli-device-auth"}
_SECRET_KEYS = {
    "discord": "DISCORD_BOT_TOKEN",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "composio": "COMPOSIO_API_KEY",
    "github": "GH_TOKEN",
    "vercel": "VERCEL_TOKEN",
    "slack": "SLACK_BOT_TOKEN",
    "telegram": "TELEGRAM_BOT_TOKEN",
}
_DEVICE_AUTH_HOSTS = {
    "github.com",
    "vercel.com",
    "auth.openai.com",
    "platform.openai.com",
    "discord.com",
}
_MAX_RECORD_BYTES = 64 * 1024
_MAX_ACTIVE_SESSIONS = 1024
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class LinkUnavailable(ValidationError):
    """The setup link is invalid, expired, or already consumed."""


def _validate_https_url(value: str, label: str) -> Any:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValidationError(f"{label} must be a bounded HTTPS URL")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError(f"{label} contains an invalid port") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ValidationError(f"{label} must be an HTTPS URL without credentials or a custom port")
    return parsed


def validate_broker_base_url(value: str) -> str:
    parsed = _validate_https_url(value, "setup broker URL")
    if not parsed.hostname.lower().endswith(".ts.net"):
        raise ValidationError("setup broker URL must use a Tailscale MagicDNS .ts.net hostname")
    if parsed.query or parsed.fragment:
        raise ValidationError("setup broker URL may not contain a query or fragment")
    return value.rstrip("/")


def validate_setup_target(value: str, purpose: str) -> str:
    if purpose not in _PURPOSES:
        raise ValidationError(f"Unsupported setup-link purpose: {purpose}")
    if purpose == "station-secret":
        raise ValidationError("station-secret setup does not use a redirect target")
    parsed = _validate_https_url(value, "setup target URL")
    hostname = parsed.hostname.lower()
    if purpose == "hermes-credentials" and not hostname.endswith(".ts.net"):
        raise ValidationError("Hermes credential setup must stay behind a .ts.net URL")
    if purpose == "composio-oauth" and hostname != "connect.composio.dev":
        raise ValidationError("Composio setup may redirect only to connect.composio.dev")
    if purpose == "cli-device-auth" and hostname not in _DEVICE_AUTH_HOSTS:
        raise ValidationError("CLI device authorization target is not allowlisted")
    return value


def _reject_symlink_chain(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise SecurityError(f"Symlink forbidden in setup-link state path: {current}")


@dataclass(frozen=True)
class CreatedSetupLink:
    session_id: str
    url: str
    expires_at: int
    zone_id: str
    principal_id: str
    provider: str
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "url": self.url,
            "expires_at": self.expires_at,
            "zone_id": self.zone_id,
            "principal_id": self.principal_id,
            "provider": self.provider,
            "purpose": self.purpose,
            "claim": "SHORT_LIVED_LINK_CREATED_NOT_CONSUMED",
        }


class SetupLinkStore:
    """Filesystem-backed, one-time sessions for a local setup broker.

    The raw bearer token exists only in the returned URL. The store persists a
    SHA-256 digest, scope metadata, and its consumed timestamp. Redirect sessions
    persist only an allowlisted target. Secret sessions write the submitted value
    directly to the owning Zone's mode-0600 Hermes environment; neither the raw
    bearer token nor the credential is persisted in the session record.
    """

    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        if not self.root.is_absolute():
            raise ValidationError("setup-link state root must be absolute")
        _reject_symlink_chain(self.root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = os.lstat(self.root)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise SecurityError("setup-link state root must be a real directory")
        if info.st_uid != os.geteuid():
            raise SecurityError("setup-link state root must be owned by the broker user")
        os.chmod(self.root, 0o700)

    def _credential_file(self) -> Path:
        if self.root.name != "setup-links" or self.root.parent.name != "connector-state":
            raise SecurityError("station-secret state must be <zone-root>/connector-state/setup-links")
        zone_root = self.root.parent.parent
        credential_file = zone_root / "hermes" / ".env"
        _reject_symlink_chain(credential_file.parent)
        credential_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent_info = os.lstat(credential_file.parent)
        if parent_info.st_uid != os.geteuid() or not stat.S_ISDIR(parent_info.st_mode):
            raise SecurityError("Zone Hermes home must be a real directory owned by the broker user")
        if credential_file.exists() or credential_file.is_symlink():
            info = os.lstat(credential_file)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise SecurityError("Zone Hermes credential file must be an owned regular file")
        return credential_file

    @staticmethod
    def _write_env_secret(path: Path, key: str, secret: str) -> None:
        if (
            not secret
            or len(secret.encode("utf-8")) > 16 * 1024
            or not secret.isascii()
            or any(character.isspace() for character in secret)
            or any(character in secret for character in ("\x00", "\r", "\n"))
        ):
            raise ValidationError("credential value must be bounded, ASCII and contain no whitespace")
        existing = ""
        if path.exists():
            fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
            try:
                if os.fstat(fd).st_size > 1024 * 1024:
                    raise SecurityError("Zone Hermes credential file is unexpectedly large")
                try:
                    existing = os.read(fd, 1024 * 1024 + 1).decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SecurityError("Zone Hermes credential file is not valid UTF-8") from exc
            finally:
                os.close(fd)
        rendered: list[str] = []
        replaced = False
        for line in existing.splitlines():
            if line.startswith(key + "="):
                if not replaced:
                    rendered.append(f"{key}={secret}")
                    replaced = True
                continue
            rendered.append(line)
        if not replaced:
            rendered.append(f"{key}={secret}")
        payload = ("\n".join(rendered).rstrip("\n") + "\n").encode("utf-8")
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
        try:
            view = memoryview(payload)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    @contextmanager
    def _lock(self) -> Iterator[None]:
        fd = os.open(self.root / ".lock", os.O_RDWR | os.O_CREAT | _NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _path(self, session_id: str) -> Path:
        if not _SESSION_ID.fullmatch(session_id):
            raise LinkUnavailable("setup link is unavailable")
        return self.root / f"{session_id}.json"

    def _read(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        try:
            fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
        except (FileNotFoundError, OSError) as exc:
            raise LinkUnavailable("setup link is unavailable") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_RECORD_BYTES:
                raise LinkUnavailable("setup link is unavailable")
            payload = os.read(fd, _MAX_RECORD_BYTES + 1)
        finally:
            os.close(fd)
        try:
            record = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LinkUnavailable("setup link is unavailable") from exc
        if not isinstance(record, dict) or record.get("session_id") != session_id:
            raise LinkUnavailable("setup link is unavailable")
        return record

    def _write(self, record: dict[str, Any]) -> None:
        target = self._path(str(record["session_id"]))
        temporary = self.root / f".{target.name}.{uuid.uuid4().hex}.tmp"
        data = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, target)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _prune_and_count(self, now: int) -> int:
        active = 0
        for path in self.root.glob("*.json"):
            if path.is_symlink() or not path.is_file() or not _SESSION_ID.fullmatch(path.stem):
                continue
            try:
                record = self._read(path.stem)
                expired = now >= int(record.get("expires_at") or 0)
                consumed = record.get("consumed_at") is not None
            except (LinkUnavailable, TypeError, ValueError):
                continue
            if expired or consumed:
                os.unlink(path)
            else:
                active += 1
        return active

    @staticmethod
    def _verify(record: dict[str, Any], token: str, now: int) -> None:
        if not _TOKEN.fullmatch(token):
            raise LinkUnavailable("setup link is unavailable")
        expected = str(record.get("token_sha256") or "")
        observed = hashlib.sha256(token.encode("ascii")).hexdigest()
        if not hmac.compare_digest(expected, observed):
            raise LinkUnavailable("setup link is unavailable")
        if record.get("consumed_at") is not None:
            raise LinkUnavailable("setup link has already been used")
        if now >= int(record.get("expires_at") or 0):
            raise LinkUnavailable("setup link has expired")

    def create(
        self,
        *,
        base_url: str,
        target_url: str | None,
        zone_id: str,
        principal_id: str,
        provider: str,
        purpose: str,
        ttl_seconds: int = 600,
        now: int | None = None,
    ) -> CreatedSetupLink:
        base_url = validate_broker_base_url(base_url)
        zone_id = validate_identifier(zone_id, "zone_id")
        principal_id = validate_identifier(principal_id, "principal_id")
        provider = validate_identifier(provider, "provider")
        if purpose == "station-secret":
            if provider not in _SECRET_KEYS:
                raise ValidationError(f"Provider {provider!r} does not have an allowlisted Station secret key")
            target_url = None
        else:
            target_url = validate_setup_target(str(target_url or ""), purpose)
        if not 60 <= ttl_seconds <= 900:
            raise ValidationError("setup-link TTL must be between 60 and 900 seconds")
        created_at = int(time.time() if now is None else now)
        session_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        expires_at = created_at + ttl_seconds
        record = {
            "schema_version": 1,
            "session_id": session_id,
            "zone_id": zone_id,
            "principal_id": principal_id,
            "provider": provider,
            "purpose": purpose,
            "target_url": target_url,
            "target_host": urlsplit(target_url).hostname if target_url else None,
            "credential_key": _SECRET_KEYS.get(provider) if purpose == "station-secret" else None,
            "token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
            "created_at": created_at,
            "expires_at": expires_at,
            "consumed_at": None,
        }
        with self._lock():
            if self._prune_and_count(created_at) >= _MAX_ACTIVE_SESSIONS:
                raise LinkUnavailable("setup-link capacity is temporarily exhausted")
            self._write(record)
        return CreatedSetupLink(
            session_id=session_id,
            url=f"{base_url}/s/{session_id}/{token}",
            expires_at=expires_at,
            zone_id=zone_id,
            principal_id=principal_id,
            provider=provider,
            purpose=purpose,
        )

    def peek(self, session_id: str, token: str, *, now: int | None = None) -> dict[str, Any]:
        timestamp = int(time.time() if now is None else now)
        with self._lock():
            record = self._read(session_id)
            self._verify(record, token, timestamp)
        return {
            "session_id": session_id,
            "zone_id": record["zone_id"],
            "provider": record["provider"],
            "purpose": record["purpose"],
            "expires_at": record["expires_at"],
        }

    def consume(self, session_id: str, token: str, *, now: int | None = None) -> str:
        timestamp = int(time.time() if now is None else now)
        with self._lock():
            record = self._read(session_id)
            self._verify(record, token, timestamp)
            target_url = validate_setup_target(str(record.get("target_url") or ""), str(record.get("purpose") or ""))
            record["consumed_at"] = timestamp
            self._write(record)
        return target_url

    def submit_secret(self, session_id: str, token: str, secret: str, *, now: int | None = None) -> str:
        timestamp = int(time.time() if now is None else now)
        with self._lock():
            record = self._read(session_id)
            self._verify(record, token, timestamp)
            if record.get("purpose") != "station-secret":
                raise LinkUnavailable("setup link does not accept a credential")
            provider = str(record.get("provider") or "")
            key = _SECRET_KEYS.get(provider)
            if not key or key != record.get("credential_key"):
                raise LinkUnavailable("setup link credential mapping is invalid")
            self._write_env_secret(self._credential_file(), key, secret)
            record["consumed_at"] = timestamp
            self._write(record)
        return provider


def setup_link_card(link: CreatedSetupLink) -> dict[str, Any]:
    """Provider-neutral card that Discord/Slack/Telegram adapters can render."""
    return {
        "schema_version": 1,
        "type": "station.guided_setup",
        "title": f"Connect {link.provider}",
        "body": "Open the protected setup page. Never paste a credential into chat.",
        "expires_at": link.expires_at,
        "actions": [{"type": "link", "label": "Open secure setup", "url": link.url}],
        "visibility": "requesting-principal-only",
    }


def _page(title: str, message: str, *, action: str | None = None, secret_form: bool = False) -> bytes:
    form = ""
    if action:
        field = '<label for="secret">Credential</label><input id="secret" name="secret" type="password" required autocomplete="off" maxlength="16384">' if secret_form else ""
        label = "Save securely" if secret_form else "Continue securely"
        form = f'<form method="post" action="{html.escape(action, quote=True)}">{field}<button type="submit">{label}</button></form>'
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font:16px system-ui,sans-serif;background:#0b0b0c;color:#f5f5f5;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{width:min(32rem,calc(100% - 2rem));border:1px solid #303034;border-radius:.75rem;padding:1.5rem;background:#171719}}
p{{color:#b8b8bf;line-height:1.5}}form{{display:grid;gap:.75rem}}input{{padding:.75rem;border-radius:.5rem;border:1px solid #404047;background:#0b0b0c;color:#f5f5f5}}button{{border:0;border-radius:.5rem;padding:.75rem 1rem;font-weight:650;cursor:pointer}}
</style></head><body><main><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>{form}</main></body></html>"""
    return document.encode("utf-8")


def serve_setup_links(store: SetupLinkStore, *, host: str = "127.0.0.1", port: int = 8787) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValidationError("setup-link broker must listen on loopback")
    if not 1024 <= port <= 65535:
        raise ValidationError("setup-link broker port must be between 1024 and 65535")

    class Handler(BaseHTTPRequestHandler):
        server_version = "StationSetupLink/1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _headers(self, status: HTTPStatus, content_type: str, length: int = 0) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()

        def _parts(self) -> tuple[str, str] | None:
            parsed = urlsplit(self.path)
            pieces = parsed.path.strip("/").split("/")
            if len(pieces) == 4 and pieces[0] == "station-setup":
                pieces = pieces[1:]
            if parsed.query or parsed.fragment or len(pieces) != 3 or pieces[0] != "s":
                return None
            return pieces[1], pieces[2]

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path in {"/health", "/station-setup/health"}:
                payload = b'{"status":"ok"}\n'
                self._headers(HTTPStatus.OK, "application/json", len(payload))
                self.wfile.write(payload)
                return
            parts = self._parts()
            try:
                if parts is None:
                    raise LinkUnavailable("setup link is unavailable")
                session = store.peek(*parts)
                secret_form = session["purpose"] == "station-secret"
                body = _page(
                    f"Connect {session['provider']}",
                    "This one-time action is bound to your Station Zone. The credential goes directly to its mode-0600 Hermes environment and never through chat."
                    if secret_form
                    else "This one-time action is bound to your Station Zone and will open the approved provider setup flow.",
                    action=urlsplit(self.path).path,
                    secret_form=secret_form,
                )
                self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
                self.wfile.write(body)
            except LinkUnavailable as exc:
                body = _page("Link unavailable", str(exc))
                self._headers(HTTPStatus.GONE, "text/html; charset=utf-8", len(body))
                self.wfile.write(body)
            except (SecurityError, ValidationError, UnicodeError):
                body = _page("Setup failed", "The submitted value was rejected. Create a new one-time link and try again.")
                self._headers(HTTPStatus.BAD_REQUEST, "text/html; charset=utf-8", len(body))
                self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            parts = self._parts()
            try:
                if parts is None:
                    raise LinkUnavailable("setup link is unavailable")
                session = store.peek(*parts)
                if session["purpose"] == "station-secret":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError as exc:
                        raise LinkUnavailable("invalid setup submission") from exc
                    if not 0 < length <= 20 * 1024:
                        raise LinkUnavailable("invalid setup submission")
                    values = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                    secret = values.get("secret", [""])[0]
                    provider = store.submit_secret(*parts, secret)
                    body = _page("Credential saved", f"{provider} is now configured in this Zone. Return to your bot and run its verification action.")
                    self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
                    self.wfile.write(body)
                    return
                target = store.consume(*parts)
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", target)
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
            except LinkUnavailable as exc:
                body = _page("Link unavailable", str(exc))
                self._headers(HTTPStatus.GONE, "text/html; charset=utf-8", len(body))
                self.wfile.write(body)
            except (SecurityError, ValidationError, UnicodeError):
                body = _page("Setup failed", "The submitted value was rejected. Create a new one-time link and try again.")
                self._headers(HTTPStatus.BAD_REQUEST, "text/html; charset=utf-8", len(body))
                self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()
