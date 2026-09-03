# Safe Reconciler Design

The reconciler consumes one validated `InstallSpec` and the canonical `config/station.default.json`.

```text
InstallSpec
    + canonical Station config
    ↓
typed PlanStep sequence
    ↓
operation lock + STARTED receipt
    ↓
convergent reconciliation
    ↓
full Doctor
    ↓
COMPLETED receipt + READY_FOR_SETUP
```

Security properties:

- identifiers validated before path joins;
- writes restricted to explicit FHS roots;
- managed path traversal refuses symlinks;
- files replaced atomically;
- release content frozen and never overwritten by same version;
- subprocess values remain arguments;
- partial failures roll back Station-owned filesystem changes best-effort and record `DEGRADED`;
- package/user operations are documented as convergent rather than falsely transactional.
