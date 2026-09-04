# hermes-runtime

AGK OS sources compile deterministically into Hermes Profile Distributions for Director and worker profiles. Bootstrap pins the reviewed Hermes release commit in a shared executable directory and installs Hermes' explicit `voice` and `messaging` extras; every Zone retains an independent `HERMES_HOME`.

New Zones receive credential-free voice defaults: OpenAI `gpt-transcribe` for primary STT, OpenAI `gpt-4o-mini-tts` with the `alloy` voice, and a registered local Parakeet command provider. Discord audio automatically tries the loopback Parakeet service only when the primary transcription fails. Live profiles, provider keys, gateways and fresh-session acceptance still require enrollment and readback.
