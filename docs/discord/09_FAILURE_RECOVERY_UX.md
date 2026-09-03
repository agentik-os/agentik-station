# Failure and Recovery UX

Failures are product states, not exceptions dumped into chat.

## On recoverable failure

- mark the active graph node failed/blocked;
- preserve completed nodes;
- show the concise cause;
- show automatic retry policy and current round;
- expose approval/escalation if required;
- attach or link diagnostic evidence for operators.

## On hard failure

The card becomes `FAILED` and records:

- last known safe state;
- failed node;
- rollback/recovery status;
- what was not changed;
- how to resume.

Never fabricate completion because an agent stopped producing messages.
