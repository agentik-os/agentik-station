# Interaction Design

## Core interaction families

### Mission controls
- Details
- Graph
- Evidence
- Pause
- Resume
- Cancel

### Approval controls
- Approve
- Reject
- Ask for changes
- Show impact

### Input controls
Use selects/modals for scope, account, environment, option sets and free-form data. Never encode sensitive values in labels or custom IDs.

## Approval behavior

Interaction click -> authenticate Discord user -> resolve Station principal -> resolve OS/mission -> check capability/approval policy -> execute server-side transition -> persist evidence -> update card.

The LLM cannot approve its own action and cannot treat a button label as authority.

## Ephemeral detail

Use ephemeral interaction responses for operator-only context, secrets-adjacent metadata, diagnostic traces, large choice menus and permission errors. The shared mission card stays concise.

## Custom IDs

Custom IDs contain opaque action/state references only. Do not put credentials, account identifiers, raw prompts or confidential payloads into component custom IDs.
