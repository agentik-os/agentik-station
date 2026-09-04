# AGK client boundary: {{CLIENT_NAME}} (`{{CLIENT_ID}}`)

These instructions apply to every provider and agent working in this tree.

## Isolation

1. Work only inside this client boundary and its explicitly declared runtimes.
2. Never read another client's workspace, memory, connection or credential.
3. Load secrets only with `eval "$(agk client env {{CLIENT_ID}})"`.
4. Verify `.client/manifest.yaml`, `.client/integrations.yaml` and the active
   client before any external action.
5. Never print, persist or commit a secret.

## No durable work record, no code

No coding, commit, pull request or deployment may start without a valid tracker
issue recorded in the AGK durable work record. Linear is the default adapter;
use the adapter explicitly selected by `.client/workflow.yaml`. Use the canonical issue in the branch
name, commits, pull request, CI evidence, review and deployment Run.

## Delivery

Linear issue -> branch -> commits -> pull request -> CI -> QA -> security ->
staging -> CTO review -> engineering approval -> deployment authorization ->
production -> health verification -> Linear done.

`REQUEST CHANGES` resumes the same mission and Hermes session with the same
client, issue, repository and branch. Do not create a replacement session.

## Infrastructure

Apply `.client/permissions.yaml`. Every infrastructure action becomes an AGK
Run record. L3 and L4 actions require an explicit human authorization. Database
deletion is forbidden.

## Reporting

Keep the Linear issue current. Attach pull request, CI, QA, security, preview,
risk and rollback evidence before requesting CTO review. Discord is the human
decision interface; it is not a substitute for updating Linear.

Default to deciding and continuing with the smallest reversible safe action.
Use `BLOCKED` only when no useful next action remains, and include
`blocked_by`, `already_tried`, `impact`, `need` and `resume`. Resume the same
work record, branch, PR and Hermes session.
