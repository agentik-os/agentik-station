# Discord Status Projection

Discord shows **semantic mission truth**, not raw executor narration.

## Status header

The Mission Progress Card may show:

```text
Plan • not run
Code • running
Code • reported done
Test • verified
Ship • read back
Mission • accepted
```

The label is derived from durable orchestration state and evidence, never selected freely by the LLM.

## Example

```text
DEVOPS OS · Atlas
Multi-OS routing

Code • reported done
████████░░ 80%

✓ Clarify & acceptance
✓ Leverage scan
✓ Implementation
↻ Verification
○ Integration review

Owner: Forge
Verifier: Sentinel

Current
Executor reports implementation complete. Verification has not passed yet.

[Details] [Graph] [Evidence] [Logs]
```

Once verified, the same card is edited:

```text
Test • verified
✓ test suite
✓ independent review
↻ staging readback
```

This prevents the UI from collapsing “work ended” and “work proven correct” into one green state.
