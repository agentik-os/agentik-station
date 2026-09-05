# Hermes voice and bot-guided setup

Hermes remains the single runtime brain. Station adds two host capabilities around it:

1. a reviewed voice path with OpenAI audio as primary and local Parakeet ASR as Discord failover;
2. a one-time setup-link broker that lets an authorized bot show a short Tailnet-only button instead of asking a human to manipulate the terminal or paste a secret into chat.

Neither capability weakens the Zone boundary. Every bot still runs as the owning Zone Unix user with that Zone's `HERMES_HOME`.

Diagram source: [`docs/diagrams/15_GUIDED_SETUP_AND_VOICE.mmd`](../diagrams/15_GUIDED_SETUP_AND_VOICE.mmd).

## Default voice topology

```text
voice input / Discord voice note
  → owning Hermes gateway/profile
  → OpenAI gpt-transcribe (primary)
  → if Discord primary STT fails: 127.0.0.1:5092 Parakeet (local fallback)
  → transcript enters the same Hermes session
  → Hermes central reasoning + OS team/tools
  → OpenAI gpt-4o-mini-tts, voice alloy
  → voice response on the originating Hermes surface
```

Bootstrap installs Hermes' explicit `voice` and `messaging` extras plus `ffmpeg`, Opus and PortAudio. It seeds new Zone configs from [`config/hermes/voice.default.yaml`](../../config/hermes/voice.default.yaml), but never overwrites an existing `config.yaml`.

The bootstrap check is deliberately **headless**: it imports the server-side Python dependencies, exercises PyNaCl `Aead`, verifies the installed sounddevice package and its PortAudio library binding without initializing audio devices, and runs synthetic Discord Opus and ffmpeg PCM/Opus round-trips. Missing or broken required dependencies still fail installation. It does not connect a Discord bot, call an audio provider, download a speech model, or start an audio daemon.

Local microphone/speaker access is reported as `LOCAL_AUDIO=NOT_TESTED`, not as operational. Hermes uses sounddevice/PortAudio for local CLI capture/playback; its Discord adapter uses network audio, PyNaCl, Opus, NumPy and ffmpeg. A headless VPS therefore does not need a local PulseAudio session for Discord or file-audio installation checks. An interactive Host that needs local CLI voice must separately configure and test its real audio devices. The upstream distinction is documented in [Hermes Voice Mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode).

The primary STT model is OpenAI `gpt-transcribe`; the default TTS model is `gpt-4o-mini-tts` with `alloy`. The Zone provides `OPENAI_API_KEY` (or the narrower Hermes-supported `VOICE_TOOLS_OPENAI_KEY`) through its mode-0600 environment or Hermes credential pool. OpenAI documents `gpt-transcribe` at $0.0045 per audio minute; actual billing and availability remain external readback, not a Station claim. See [OpenAI GPT Transcribe](https://developers.openai.com/api/docs/models/gpt-transcribe) and [OpenAI text to speech](https://developers.openai.com/api/docs/guides/text-to-speech).

Parakeet is **speech-to-text**, not text-to-speech. Station pins its reviewed v0.8.0 source commit and multi-architecture int8 image digest, publishes it only on `127.0.0.1:5092`, drops container capabilities, makes the filesystem read-only, and enforces PID/memory limits. The int8 image needs about 2 GB RAM in normal operation. See [achetronic/parakeet](https://github.com/achetronic/parakeet).

Useful checks:

```bash
systemctl status station-parakeet.service --no-pager
curl --fail http://127.0.0.1:5092/health
sudo station deps install --component parakeet
```

Hermes voice controls, including Discord voice replies and voice-channel mode, remain the native Hermes interface. See [Hermes Voice Mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode).

## Why setup starts in Discord, but is not Discord-locked

The broker produces a provider-neutral `station.guided_setup` card: title, body, expiry and one approved link action. Discord renders it as an ephemeral SDK button today. The same payload can be rendered as a Slack Block Kit button, Telegram inline keyboard or plain private link without changing the broker or credential rules. Ordinary agent conversation already uses Hermes' platform-independent Messaging Gateway.

The current external-readback claim is deliberately narrower: the Discord button path is implemented; live Slack/Telegram renderers still require platform acceptance. Their standard Hermes gateway setup continues to work.

## The unavoidable first credential

A Discord bot cannot create its own Discord application or mint its own token. A human server owner must create/authorize the first application and enter its token through Hermes' secure Zone setup. Temporary Administrator may be granted only for an explicit topology bootstrap window and must be removed and read back afterward.

Once that first gateway and Tailscale are enrolled, routine provider setup can move into the bot experience.

## Enable the protected setup broker

The service listens only on loopback. Tailscale Serve publishes the `/station-setup` path inside the tailnet; Station never uses Funnel for this broker.

```bash
# First enroll the Host in the approved Tailnet through Tailscale's own flow.
sudo ./scripts/station_guided_setup_enable.sh

# Optional: send provider setup to an already protected Hermes Dashboard page.
sudo ./scripts/station_guided_setup_enable.sh \
  --hermes-setup-url https://station.example.ts.net/hermes/config
```

Bootstrap calls this script with `--if-enrolled`. If Tailscale is not ready, bootstrap still starts the local broker and reports the exact enrollment action; it never exposes a public fallback.

## One-time link lifecycle

```text
authorized user presses Connect in a private/ephemeral bot response
  → Zone bot asks `station setup-link create`
  → random bearer token appears only in the returned Tailnet URL
  → broker stores SHA-256(token), Zone/principal/provider scope and ≤10 minute expiry
  → user opens HTTPS .ts.net link
  → either enters an allowlisted Zone secret or continues to an allowlisted OAuth/device URL
  → broker consumes link once
  → secret goes directly to <zone>/hermes/.env mode 0600, never session JSON/chat/log/evidence
  → gateway is restarted and provider readback decides readiness
```

Only approved mappings are accepted (`OPENAI_API_KEY`, Anthropic, OpenRouter, Composio, GitHub, Vercel, Discord, Slack and Telegram). Redirects are restricted to the protected Hermes dashboard, `connect.composio.dev`, or allowlisted CLI device-auth hosts. Composio Connect Links must enter Station through `--target-url-file` or an in-process adapter, never a process argument. Composio documents that Connect Link credentials do not pass through the agent/application; see [Composio authentication](https://docs.composio.dev/docs/authentication).

The broker suppresses request URL logs, sets no-store/no-referrer/CSP/frame-deny headers, persists only owned regular files, rejects symlink paths, binds sessions to a Zone/principal/provider, expires them in at most 15 minutes, and consumes them once. Tailnet ACLs and the ephemeral platform response are still required: possession of the link is authorization to redeem it.

## Acceptance

Installation proves only `INSTALLABLE`/`READY_FOR_SETUP`. Before claiming voice or guided setup operational, verify:

1. Tailscale device identity, ACL and HTTPS Serve path;
2. setup link expiry, one-time use, wrong-principal delivery prevention and absence of secrets in chat/log/session/evidence;
3. provider login or key readback from the owning Zone;
4. OpenAI STT and TTS round-trip;
5. forced OpenAI failure followed by a successful Parakeet Discord transcription;
6. Discord voice note and voice-channel reply;
7. gateway restart/reboot persistence and least-privilege guild permissions.
