# Voice Stack

Voice is optional.

It should not block Agentik Node V1.

## Parakeet

Role:
- speech-to-text service
- sidecar
- OpenAI/Whisper-compatible transcription API

Capability:

```text
voice.transcribe
```

Possible flows:

```text
voice journal
→ Parakeet
→ Journal OS
```

```text
meeting audio
→ Parakeet
→ Meeting / Knowledge OS
→ Notion + Linear
```

## VoiceStudio

Role:
- TTS
- voice cloning
- voice design
- diarization
- dubbing
- richer audio operations
- MCP/API capability

Keep it as a separate service/container.

## Combined

```text
Hermes
→ VoiceStudio MCP
→ Parakeet ASR
```

## Product rule

Do not make proprietary Agentik core depend structurally on VoiceStudio source code.
Treat it as an optional capability and review licensing before commercial embedding/modification.
