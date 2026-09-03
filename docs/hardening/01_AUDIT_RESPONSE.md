# Audit Response Matrix

| Audit finding | v11 response | Evidence |
|---|---|---|
| Root path traversal | strict identifiers + SafeFS root containment | identifier and filesystem security tests |
| Remote command injection | JSON InstallSpec + fixed argv commands | remote bootstrap security tests |
| Symlink overwrite | descriptor traversal, no-follow, regular-file checks | ancestor/destination symlink tests |
| Wrong Project owner | Project reconciled using parent Zone identity | temp-root install test |
| Station system home inaccessible | parent mode/group and exact system identity contract | installed layout Doctor |
| Root network installers | removed from safe-kernel apply | repository unsafe-pattern Doctor |
| False OS installed state | desired packages remain `NOT_INSTALLED` | OS catalog and integration test |
| Shallow Doctor | FHS, releases, Zones, Projects, modes, symlinks, ownership, receipts, state | repo/installed Doctor tests |
| Remote Fleet overclaim | explicit bootstrap-transport/report status | remote plan contract |
| Missing recovery | kept SPECIFIED with explicit next repair action | module catalog |

Remaining modules are intentionally staged for later releases rather than simulated in v11.
