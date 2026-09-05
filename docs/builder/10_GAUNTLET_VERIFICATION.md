# Builder Gauntlet + Verification Engineering

Every OS build passes the Engineering Harness from `14_ENGINEERING/`.

## Builder Gauntlet

```text
SPEC
-> independent spec critic
-> RED acceptance/eval
-> BUILD
-> verify-on-stop / local checks
-> independent implementation critic
-> targeted correction
-> OS contract audit
-> security/capability audit
-> package audit
-> doctor
-> rollback rehearsal
-> recovery rehearsal
-> Discord readback
-> fresh-session acceptance
-> release critic
```

Retries are bounded. Repeated failure escalates instead of silently relaxing the test.

## Ponytail

Ponytail is an intended required integration for Builder coding/review profiles,
but is **NOT_INSTALLED** on the reviewed Host. Its commands and modes are
unavailable because the retained native Hermes security scan rejected the reviewed
immutable pin. Profile installation does not install or enable the plugin.

Repair requires an upstream-reviewed scanner correction or published plugin
distribution, a reviewed immutable pin, the full native security scan and then
scoped runtime/command/ACL acceptance. Preserve the guard; no filtered source,
manual copy, trust exception or bypass. See the
[native scan evidence](../audit/2026-09-05-ponytail-native-scan.md).

Independent builds can apply Station's reviewed reuse/minimalism guidance before
new code, without calling it Ponytail or marking its checks passed. Explicitly
Ponytail-dependent acceptance remains pending. Neither that guidance nor a future
accepted plugin authorizes removing validation, security, accessibility, recovery
or evidence requirements.

## Independent review

The final critic should use a fresh session and preferably a separate profile/model role. It receives the contract/spec, artifact and evidence, not the Builder's private reasoning history.
