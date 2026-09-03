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

Builder coding profiles install Ponytail through Hermes and apply the reuse/minimalism ladder before new code. Ponytail never authorizes removing validation, security, accessibility, recovery or evidence requirements.

## Independent review

The final critic should use a fresh session and preferably a separate profile/model role. It receives the contract/spec, artifact and evidence, not the Builder's private reasoning history.
