#!/usr/bin/env python3
"""Headless Hermes audio dependency checks; never open an audio device or account."""

from ctypes.util import find_library
from importlib import import_module
from importlib.metadata import version
from importlib.util import find_spec
from shutil import which
from subprocess import PIPE, run
import sys


PCM_FRAME = bytes(960 * 2 * 2)  # Synthetic 20 ms, 48 kHz, stereo signed-16 silence.


def check_server_python():
    for name in ("discord", "numpy", "faster_whisper"):
        import_module(name)
    # The pinned Discord adapter uses Aead, not merely the nacl package name.
    aead = import_module("nacl.secret").Aead
    box = aead(bytes(aead.KEY_SIZE))
    message = b"station-synthetic-audio-check"
    encrypted = box.encrypt(message, nonce=bytes(aead.NONCE_SIZE))
    if box.decrypt(encrypted) != message:
        raise RuntimeError("PyNaCl Aead round-trip failed")


def check_local_audio_package():
    if not version("sounddevice") or find_spec("sounddevice") is None:
        raise RuntimeError("sounddevice is not installed")
    portaudio = find_library("portaudio")
    if not portaudio:
        raise RuntimeError("PortAudio library is missing")
    # sounddevice 0.5.5 imports this generated CFFI binding, then initializes
    # PortAudio. Check its library binding WITHOUT Pa_Initialize/device access.
    library = import_module("_sounddevice").ffi.dlopen(portaudio)
    if library.Pa_GetVersion() <= 0:
        raise RuntimeError("PortAudio version readback failed")


def check_discord_codec():
    opus = import_module("discord").opus
    if not opus.is_loaded():
        library = find_library("opus")
        if not library:
            raise RuntimeError("Opus library is missing")
        opus.load_opus(library)
    if not opus.is_loaded():
        raise RuntimeError("Discord could not load Opus")
    packet = opus.Encoder().encode(PCM_FRAME, 960)
    decoded = opus.Decoder().decode(packet)
    if not packet or len(decoded) != len(PCM_FRAME):
        raise RuntimeError("Discord Opus round-trip failed")


def check_file_audio():
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is missing")
    common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    encoded = run([
        *common, "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0",
        "-c:a", "libopus", "-f", "ogg", "pipe:1",
    ], input=PCM_FRAME, stdout=PIPE, stderr=PIPE, check=True, timeout=20).stdout
    if not encoded.startswith(b"OggS"):
        raise RuntimeError("ffmpeg did not produce Ogg audio")
    decoded = run([
        *common, "-f", "ogg", "-i", "pipe:0", "-f", "s16le", "-ar", "48000",
        "-ac", "2", "pipe:1",
    ], input=encoded, stdout=PIPE, stderr=PIPE, check=True, timeout=20).stdout
    if len(decoded) != len(PCM_FRAME):
        raise RuntimeError("ffmpeg audio round-trip failed")


def main():
    for label, check in (
        ("server Python/PyNaCl", check_server_python),
        ("sounddevice package/PortAudio library", check_local_audio_package),
        ("Discord Opus codec", check_discord_codec),
        ("ffmpeg file audio", check_file_audio),
    ):
        try:
            check()
        except Exception as exc:
            # Do not echo arbitrary dependency diagnostics or environment data.
            print(f"ERROR: Hermes voice dependency check failed: {label} ({type(exc).__name__}). "
                  "Repair this dependency before retrying.", file=sys.stderr)
            return 1
    print("Hermes server audio dependencies OK (synthetic checks only; live acceptance pending)")
    print("LOCAL_AUDIO=NOT_TESTED: local microphone/speaker access requires separate device setup; "
          "it is not required for Discord or file audio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
