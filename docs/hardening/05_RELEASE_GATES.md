# Release Gates

## v11 safe-kernel gate

- repository Doctor;
- identifier/model/unit tests;
- privileged-filesystem adversarial tests;
- remote-bootstrap adversarial tests;
- contract/schema tests;
- temp-root client/core reconciliation;
- immutable release/idempotency test;
- installed Station Doctor;
- Builder/Librarian deterministic pack tests;
- JSON/YAML/schema parse;
- Python AST validation;
- no generated caches, symlinks, unsafe execution patterns, or forbidden legacy references;
- archive integrity.

## Later external acceptance

Real external tests remain mandatory before operational claims:

- fresh Ubuntu VPS install and reboot;
- Hermes profile/plugin/board/gateway compilation;
- dedicated Discord bot provisioning and Components V2 readback;
- Composio principal/session/MCP/trigger readback;
- negative cross-Zone account tests;
- encrypted off-Host backup and destructive restore;
- controlled remote Node reconciliation and rollback.
