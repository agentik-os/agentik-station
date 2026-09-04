# parakeet

Parakeet is the local multilingual ASR/STT path; it is not a text-to-speech engine. Station runs the reviewed int8 container by immutable digest, binds it only to `127.0.0.1:5092`, registers it as the Hermes `parakeet` command provider, and uses it as the Discord audio fallback when the primary OpenAI transcription request fails.

The service is shared, secretless infrastructure with strict container resource/capability limits. It keeps no Station credentials. Per-Zone audio/transcript retention remains governed by the owning Hermes profile and evidence policy.
