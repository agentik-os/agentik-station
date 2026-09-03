# Mission Progress Card

One mission gets one primary live status message.

## Card states

```text
PLANNING
READY
RUNNING
WAITING_APPROVAL
BLOCKED
VERIFYING
RETRYING
DONE
FAILED
CANCELLED
```

## Human-visible layout

```text
[OS identity]  Mission title                         RUNNING

Objective
One sentence describing the outcome.

Progress  ███████░░░  70%   ·   5/7 nodes complete

Plan
✓ 01 Inspect current system
✓ 02 Design minimal change
✓ 03 Implement backend
↻ 04 Run verification
○ 05 Independent review
○ 06 Live acceptance
○ 07 Evidence + close

Current
Verification suite running.

Loop
Gauntlet round 1/3 · no blocker

[Details] [Graph] [Evidence] [Pause/Cancel when authorized]
```

## Update policy

The controller edits the existing message instead of sending one message per tool. Updates are coalesced and rate-aware. A semantic state change flushes immediately; noisy low-level tool events only update logs/evidence.

Recommended semantic update events:

- plan_created;
- node_started;
- node_completed;
- node_blocked;
- plan_revised;
- approval_requested;
- verification_started/passed/failed;
- gauntlet_retry;
- mission_completed/failed/cancelled.

## Finalization

On success the same card becomes a Final Mission Report with:

- outcome;
- completed plan summary;
- key artifacts/links;
- verification evidence;
- material problems encountered and how they were resolved;
- deviations from the original plan;
- follow-up items, only when real;
- duration/cost metadata only if configured for that audience.

On failure the card remains visible with failure reason, last safe state, recovery action and authorized retry controls.
