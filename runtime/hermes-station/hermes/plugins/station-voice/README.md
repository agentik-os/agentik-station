# Station voice provider

An opt-in native Hermes `TranscriptionProvider` named
`station-openai-parakeet`. It uses the active profile's native OpenAI helper,
then the installed `/usr/local/libexec/station-parakeet-transcribe` adapter
when the primary returns a valid failure or raises an I/O exception.

Install and enable `station-voice` through the owning profile's normal Hermes
plugin workflow, then select it in that profile's configuration:

```yaml
plugins:
  enabled:
    - station-voice
stt:
  enabled: true
  provider: station-openai-parakeet
  station-openai-parakeet:
    model: gpt-transcribe
```

Merge these keys into existing configuration; do not replace existing plugin
selections or copy another profile's credentials. Enrollment does not itself
prove an authenticated provider or Discord bot.

## Scope and routing

The provider applies to **all audio routed through `transcribe_audio` in the
selected profile**, including native message attachments and voice channels.
It is not Discord-only. Other profiles and built-in STT routes are unchanged.
Hermes retains ingress authorization, media downloads, deduplication and session
routing. This plugin registers no gateway hooks, patches no functions and mutates
no configuration or environment.

The native dispatcher supplies `stt.station-openai-parakeet.model`; an explicit
model argument wins, otherwise the provider defaults to `gpt-transcribe`.
`stt.openai.model` does not select this composite's model. Language and prompt
hints are passed to the native OpenAI helper. Parakeet accepts the adapter's
language grammar but does not receive the OpenAI prompt or model selection.
Native `cloud_trim_silence` applies to built-in cloud providers, not this plugin;
the composite does not promise that optimization.

OpenAI success, including an empty transcript indicating silence, does not
trigger Parakeet. Malformed return values and unexpected exceptions escaping the
native helper fail closed. The helper itself converts some internal exceptions
into valid failure envelopes; those trigger the declared local fallback.
Native gateway code may independently try faster-whisper after
this provider fails: this is not a promise of an exclusive two-backend chain.
Do not combine it with a second custom Parakeet gateway fallback for the same
profile without reviewing duplicate-failure behavior.

## Safety and dependencies

- OpenAI authentication and endpoint resolution stay inside the selected
  Hermes profile's native helper. No credentials are read or copied by this plugin.
- Local fallback invokes only the fixed installed adapter with an argument
  array, no shell string and no arbitrary URL or command option.
- The child gets a minimal environment and private temporary HOME; no inherited
  keys, proxies or curl configuration. The gateway's HOME remains unchanged.
- Audio must be an absolute canonical single-link regular file, nonempty and
  at most 25 MiB, owned by the caller and not group/other-writable. Ancestors
  must belong to root or the caller and not be group/other-writable, except the
  root-owned sticky `/tmp` or `/private/tmp`. This prevents another Unix identity
  substituting the path before the native helper reopens it. The adapter also
  requires a conservative path grammar. These checks do not make a readable file
  private or sandbox root/another process with the same Unix UID; Zone permissions
  remain the isolation boundary.
- Output is privately staged, opened without following links, checked for the
  current UID, single-link regular type, mode `0600`, stable bounded bytes and
  strict UTF-8. The limit is 1 MiB; output is removed with its temporary directory.
- The adapter's HTTP deadline is 300 seconds; its subprocess deadline is 310
  seconds. Availability checks inspect dependencies only, without HTTP, provider
  calls, credential enrollment, local audio initialization or model loading.

Returned errors are static and redact paths, API responses and child diagnostics.
The delegated native Hermes helper retains its own logging behavior; the plugin
does not claim to sanitize all upstream logs. The loopback Parakeet service is
shared by local Zones and is not a tenant-isolated model service.

The one private compatibility seam is `_transcribe_openai` in the reviewed
[Hermes revision](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/tools/transcription_tools.py).
The [native provider contract](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/agent/transcription_provider.py)
and scoped `PluginContext` registration remain the public integration surface.
Revalidate discovery, dispatch and local audio readback after a Hermes update;
unit fixtures alone do not establish compatibility or live Discord/OpenAI acceptance.
