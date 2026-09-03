# Fleet Model

```text
Gareth Station / Fleet Controller
├── local trust zones
└── client registry (metadata only)
    ├── client-a: stable @ station-release-X
    ├── client-b: stable @ station-release-Y
    └── client-n: maintenance-window / health / evidence refs
```

## Fleet metadata allowed centrally

- node ID and organization ID;
- Station/Hermes/OS versions;
- health status;
- update ring;
- last doctor/evidence receipt IDs;
- backup age/DR status;
- maintenance window;
- sanitized capability inventory.

## Fleet data forbidden centrally by default

- raw client memory;
- sessions/chat transcripts;
- plaintext credentials;
- private documents;
- production DB copies;
- unrestricted filesystem mounts;
- private repository checkouts unless explicitly part of a managed delivery environment.

## Cross-node operations

Use explicit authenticated control APIs/events or client-approved remote execution. Never rely on shared home directories or shared `.env` files.
