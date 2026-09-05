"""Profile-selected native Hermes STT: OpenAI, then Station's fixed local adapter."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


PROVIDER_NAME = "station-openai-parakeet"
DEFAULT_MODEL = "gpt-transcribe"
PARAKEET_ADAPTER = "/usr/local/libexec/station-parakeet-transcribe"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_TRANSCRIPT_BYTES = 1024 * 1024
LOCAL_TIMEOUT_SECONDS = 310


def _failure(message):
    # Do not return provider exceptions, paths, HTTP bodies, or child diagnostics.
    return {"success": False, "transcript": "", "provider": PROVIDER_NAME,
            "error": message}


def _success(transcript, backend):
    return {"success": True, "transcript": transcript, "provider": PROVIDER_NAME,
            "backend": backend}


def _safe_input(file_path):
    """Require a path another Unix identity cannot replace before native reopen.

    The native helper and adapter reopen by path. Canonical spelling alone would
    not protect that handoff beneath another user's writable/owned directory.
    Root and the calling UID remain trusted; this is not a same-UID sandbox.
    """
    if not isinstance(file_path, str) or not file_path.startswith("/"):
        return False
    try:
        path = Path(file_path)
        if str(path.resolve(strict=True)) != file_path:
            return False
        caller_uid = os.geteuid()
        for parent in path.parents:
            parent_info = parent.lstat()
            if (not stat.S_ISDIR(parent_info.st_mode)
                    or parent_info.st_uid not in (0, caller_uid)):
                return False
            shared_temporary = (str(parent) in {"/tmp", "/private/tmp"}
                                and parent_info.st_uid == 0
                                and parent_info.st_mode & stat.S_ISVTX)
            if parent_info.st_mode & 0o022 and not shared_temporary:
                return False
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == caller_uid and not info.st_mode & 0o022
                and 0 < info.st_size <= MAX_AUDIO_BYTES)
    except (OSError, ValueError, RuntimeError):
        return False


def _adapter_available():
    """Inspect only the fixed installed root-owned executable; do not start a service."""
    try:
        adapter = Path(PARAKEET_ADAPTER)
        if str(adapter.resolve(strict=True)) != PARAKEET_ADAPTER:
            return False
        for parent in adapter.parents:
            parent_info = parent.lstat()
            if (not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != 0
                    or parent_info.st_mode & 0o022):
                return False
        info = adapter.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022 and os.access(adapter, os.X_OK))
    except (OSError, ValueError, RuntimeError):
        return False


def _available():
    # Availability is a dependency hint, not credential, HTTP, or model acceptance.
    # A local-only installation must remain selectable without an OpenAI key.
    try:
        return _adapter_available() or importlib.util.find_spec("openai") is not None
    except Exception:
        return False


def _primary(file_path, model, language, prompt):
    # This is the only private Hermes seam. Fail closed if an update changes it.
    # The native helper owns the active profile's credentials, endpoint, SDK,
    # language defaults and supported-format retry. Do not recursively dispatch.
    from tools.transcription_tools import _transcribe_openai

    return _transcribe_openai(file_path, model, language=language, prompt=prompt)


def _read_transcript(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
                or not 0 < info.st_size <= MAX_TRANSCRIPT_BYTES):
            raise ValueError("unsafe transcript")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_TRANSCRIPT_BYTES + 1)
        after = os.fstat(descriptor)
        if (len(data) != info.st_size or len(data) > MAX_TRANSCRIPT_BYTES
                or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                    after.st_nlink, after.st_mode, after.st_uid)
                != (info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                    info.st_nlink, info.st_mode, info.st_uid)):
            raise ValueError("changed transcript")
        transcript = data.decode("utf-8", errors="strict").strip()
        if not transcript or "\x00" in transcript:
            raise ValueError("invalid transcript")
        return transcript
    finally:
        os.close(descriptor)


def _fallback(file_path, language):
    if not _safe_input(file_path):
        return _failure("Audio input is not a supported regular file.")
    # The adapter deliberately restricts path grammar for curl's multipart syntax.
    if re.fullmatch(r"/[A-Za-z0-9._/-]+", file_path) is None:
        return _failure("Audio path is unsupported by the local adapter.")
    if language not in (None, "", "auto") and re.fullmatch(
            r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})?", language) is None:
        return _failure("Language hint is unsupported by the local adapter.")
    if not _adapter_available():
        return _failure("OpenAI transcription failed and the Station local adapter is unavailable.")
    try:
        with tempfile.TemporaryDirectory(prefix="station-stt-") as temporary:
            directory = Path(temporary).resolve(strict=True)
            output = directory / "transcript.txt"
            # No profile secrets, proxy variables, curlrc or inherited command
            # search paths enter the local HTTP child. HOME is temporary, not a
            # replacement for the gateway's real Zone HOME/HERMES_HOME.
            child_env = {"PATH": "/usr/bin:/bin", "HOME": str(directory),
                         "CURL_HOME": str(directory), "XDG_CONFIG_HOME": str(directory),
                         "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
            subprocess.run(
                [PARAKEET_ADAPTER, file_path, str(output), language or "auto"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, env=child_env, check=True,
                timeout=LOCAL_TIMEOUT_SECONDS,
            )
            return _success(_read_transcript(output), "parakeet")
    except subprocess.TimeoutExpired:
        return _failure("Station local transcription timed out.")
    except Exception:
        return _failure("Station local transcription failed its execution or output checks.")


def _transcribe(file_path, *, model=None, language=None, **extra):
    if not _safe_input(file_path):
        return _failure("Audio input is not a supported regular file.")
    selected_model = DEFAULT_MODEL if model is None else model
    prompt = extra.get("prompt")
    if (not isinstance(selected_model, str) or not selected_model.strip()
            or (language is not None and not isinstance(language, str))
            or (prompt is not None and not isinstance(prompt, str))):
        return _failure("Invalid transcription options.")
    try:
        result = _primary(file_path, selected_model, language, prompt)
    except OSError:
        # The pinned helper normally returns failures; escaped I/O errors are
        # operational failures. API/signature/programming errors are not.
        return _fallback(file_path, language)
    except Exception:
        return _failure("Hermes OpenAI transcription compatibility check failed.")
    if (type(result) is not dict or type(result.get("success")) is not bool
            or not isinstance(result.get("transcript"), str)):
        return _failure("Hermes OpenAI transcription returned an invalid response.")
    if result["success"]:
        # Empty/whitespace success can mean silence; never resend it locally.
        return _success(result["transcript"], "openai")
    if result["transcript"] != "" or not isinstance(result.get("error"), str):
        return _failure("Hermes OpenAI transcription returned an invalid failure response.")
    return _fallback(file_path, language)


def _make_provider():
    # Imported only when native Hermes loads this plugin. Repository-only tests
    # supply the ABC contract without importing an entire Hermes installation.
    from agent.transcription_provider import TranscriptionProvider

    class StationVoiceProvider(TranscriptionProvider):
        @property
        def name(self):
            return PROVIDER_NAME

        @property
        def display_name(self):
            return "Station OpenAI + local Parakeet"

        def is_available(self):
            return _available()

        def default_model(self):
            return DEFAULT_MODEL

        def list_models(self):
            return [{"id": DEFAULT_MODEL, "display": "OpenAI GPT Transcribe"}]

        def get_setup_schema(self):
            return {"name": self.display_name, "badge": "paid + local fallback",
                    "tag": "Profile-wide STT; enroll OpenAI through the owning Hermes profile.",
                    "env_vars": []}

        def transcribe(self, file_path, *, model=None, language=None, **extra):
            return _transcribe(file_path, model=model, language=language, **extra)

    return StationVoiceProvider()


def register(ctx):
    # Native PluginContext binds this registration to its own profile scope.
    # Enabling the plugin alone does not change stt.provider for any profile.
    ctx.register_transcription_provider(_make_provider())
