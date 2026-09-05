# Ponytail Engineering Integration

Repository: `DietrichGebert/ponytail`

## Current delivery gate

Ponytail remains a required engineering integration for DevOps/Builder/Engineering
OSs, but is **NOT_INSTALLED** on the reviewed Host. Repository maturity is
**SCAFFOLDED**: the retained native Hermes security scan rejected the reviewed
v4.9.0 immutable pin. Plugin commands and modes are unavailable; declaring a
profile policy does not install or enable them.

Keep the guard intact. Repair requires an upstream-reviewed scanner correction
or published plugin distribution, a reviewed immutable pin, the full native
security scan, and then scoped runtime/command/ACL acceptance. Do not filter the
source, manually copy the plugin, add a trust exception or bypass scanning.
Repeating the blocked installation or restarting Hermes is not a repair. See
the [native scan evidence](../audit/2026-09-05-ponytail-native-scan.md).

## Intended purpose and currently usable Station guidance

Ponytail's intended role is to reinforce the engineering instinct to avoid
unnecessary code while preserving validation, security, accessibility and error
handling. It is not currently an active enforcement layer.

Independent engineering work can continue using Station's existing reviewed
reuse/minimal-change guidance below. Applying that guidance is not executing
Ponytail and does not satisfy Ponytail-dependent acceptance.

Canonical ladder:

```text
Understand the real system first
↓
Does this need to exist?
↓ no → do nothing
Already exists in codebase?
↓ yes → reuse
Stdlib?
↓ yes → use it
Native platform feature?
↓ yes → use it
Installed dependency?
↓ yes → use it
Can the change be extremely small?
↓ yes → keep it small
Only then write the minimum new code required
```

## Current independent engineering lifecycle

```text
PLAN FIRST
→ inspect existing system
→ architecture / task graph
→ Station reuse/minimal-change guidance
→ implement
→ deterministic tests
→ observed simplification review
→ QA
→ security review where relevant
→ independent review
→ PR / CI
→ staging
→ live verification
→ production
→ evidence
```

## Intended profile mapping — unavailable until accepted

After the delivery gate passes, these are the intended modes, not current
profile configuration or proof of separate runtime identities:

```text
devops-director  → full
architect        → full
engineer         → full
frontend/backend → full
qa               → review
auditor/security → audit
reviewer         → review + debt
maintainer       → debt + gain
```

The reviewed plugin keeps mode in process-global state and may use Unix `HOME`
for defaults. Profiles alone do not isolate either behavior. Before enablement,
verify the exact instance/profile, gateway admission and slash-command ACLs;
never grant plugin lifecycle commands to untrusted chat users. Keep the accepted
revision in the canonical `config/versions.lock` through a reviewed release.

## Guardrail

Ponytail is not permission to skip required engineering work. Never remove:
- trust-boundary validation
- access control
- data-loss protections
- security checks
- tests required by acceptance criteria
- accessibility requirements
- observability required for production


## Position inside the v4 engineering harness

Ponytail is intended to assist simplification before implementation and during
review once installed and accepted. It does not replace Verification Engineering,
Gauntlet critics, security review or tests. Until then, the current independent
path is:

```text
Understand → Station reuse guidance → Build → Verify → Gauntlet → Integrate → Live Verify
```

This path does not report Ponytail as available or close its delivery blocker.
