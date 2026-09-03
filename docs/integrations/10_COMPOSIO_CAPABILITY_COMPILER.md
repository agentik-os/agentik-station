# AGK Capability -> Composio Compiler

Example abstract capability:

```yaml
capability: gmail.send
risk: external_write
approval: required_if_unattended
```

Compiled adapter intent:

```yaml
adapter: composio
session_policy:
  subject_from: station.principal_id
  discovery: direct
  toolkits: [gmail]
  tools: [GMAIL_SEND_EMAIL]
  connected_accounts_from: live_binding_registry
  mcp: false
  sandbox: false

evidence:
  record:
    - mission_id
    - profile_id
    - toolkit
    - tool
    - connected_account_ref
    - approval_ref
    - result_status
```

The connected-account reference is an identifier only. Secret material is never copied into AGK evidence.

## Doctor checks

- no production `default` subject;
- declared principal mapping exists;
- all configured toolkits/tools are allowed by the OS capability contract;
- connected account belongs to the resolved organization/trust zone;
- external writes have the required approval policy;
- trigger routing resolves an OS and event policy;
- Composio API credential is referenced from the correct Node/trust-zone secret scope;
- fresh-session acceptance covers critical external actions.
