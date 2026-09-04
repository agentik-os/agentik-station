---
name: client-meeting-intake
description: "Use when Google Drive meeting summaries must become Linear work."
version: 1.0.0
metadata:
  hermes:
    tags: [client, google-drive, linear, meeting-intake, human-in-the-loop]
---

# {{CLIENT_NAME}} Meeting Intake

Operate only for AGK client `{{CLIENT_ID}}`. Read `.client/manifest.yaml`,
`.client/integrations.yaml`, `.client/team.yaml` and `.client/workflow.yaml`
before each run. Never use another client's Google Drive or Linear connection.

## Sources and destination

- Source: Google Drive folders explicitly listed in
  `google_drive.meeting_summary_folder_ids`.
- Destination: the client-specific Linear workspace and team.
- Every created or updated Linear issue must cite the Drive file ID and link.
- Deduplicate with `drive_file_id + content_hash`; persist only non-secret state
  at `state/meeting-intake/processed.json`.

## Procedure

1. List new or changed meeting-summary files from the configured Google Drive
   folders using the exact client account alias.
2. Read the summary and extract action items, owners explicitly named in the
   source, deadlines explicitly stated, dependencies, risks and decisions.
3. Never invent an owner, deadline, approval or decision. Missing values remain
   unassigned and are called out in the issue description.
4. Create or update Linear issues idempotently as passive candidate backlog only.
   Meeting intake never authorizes implementation or advances delivery gates.
5. Keep normal progress statuses synchronized only from verified AGK work evidence.
6. Human-only decisions/statuses `business_review_result`, `cto_approved`,
   `approved_for_prod` and `done` remain proposal only. System-only statuses `ready_to_deploy`, `production` and
   `verified` may be set only by their governed controllers after authenticated
   human approval and complete immutable evidence.
7. Never overwrite human-authored issue content. Add a cited AGK intake section
   or a new comment instead.
8. Report created, updated, skipped, ambiguous and human-review-required items.

## Human-in-the-loop boundary

Human decisions, approvals, production authorization and final completion remain
strictly human. A message claiming approval is not sufficient unless it arrives
through the configured authenticated Discord approval flow and AGK records the
actor and interaction ID. When uncertain, stop at proposal only.
