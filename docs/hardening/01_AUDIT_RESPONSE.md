# V10 Professional Audit → Station 11.12 Final Response Matrix

The V10 Professional Audit remains the controlling hardening reference. 11.12 does not erase the audit; it records which findings are fixed in code and which still require external acceptance evidence.

| Finding | Station 11.12 response | Claim |
|---|---|---|
| P0 path traversal | strict normalized IDs + SafeFS confinement | VERIFIED locally |
| P0 remote injection | typed InstallSpec, fixed argv SSH/SCP, JSON desired state | VERIFIED locally |
| P0 symlink writes | no-follow traversal, regular-file checks, atomic replacement | VERIFIED locally |
| P0 Project ownership | Project owner is the owning Zone identity | VERIFIED locally |
| P0 station-system traversal | explicit parent identity/mode contract | VERIFIED locally |
| P0 mutable root installers | removed from safe-kernel reconciliation | VERIFIED locally |
| P1-1 real plan | one typed InstallSpec drives plan/apply/remote/tests | VERIFIED locally |
| P1-2 desired reconciliation | `/etc` desired, `/var/lib` observed, `/srv` projection, immutable `/opt` release | VERIFIED locally |
| P1-3 Hermes compiler | AGK OS v2 → Director/worker Hermes Profile Distributions; Zone-local install/Doctor commands | INSTALLABLE; live Hermes gate pending |
| P1-4 incomplete OSs | six canonical OS sources pass AGK OS v2 source Doctor; Librarian v3.0.0 is canonical | INSTALLABLE |
| P1-5 Discord scaffold | real host-owned API create/edit transport + rate-limit retry + approved bindings + corrected Hermes plugin contract | INSTALLABLE; test-guild gate pending |
| P1-6 Hermes updates | failure-visible check/plan receipts and Station update policy/rings | INSTALLABLE; real upstream promotion gate pending |
| P1-7 duplicate systemd | one canonical `runtime/systemd` source | VERIFIED locally |
| P1-8 rootless runtime | per-Zone storage/config/policy roots + subordinate-ID collision audit | INSTALLABLE; live negative isolation gate pending |
| P1-9 Composio binary only | stable Station principal, toolkit/account allowlists, session/MCP adapter | INSTALLABLE; OAuth/session readback pending |
| P1-10 SSH/rsync Fleet | typed immutable remote bootstrap, strict host keys, operation IDs/receipts, status+Doctor readback | INSTALLABLE; continuous drift/rollback gate pending |
| P1-11 recovery claims | Restic backup/check and restore-to-clean-staging rehearsal operations | INSTALLABLE; destructive off-host rehearsal pending |
| P1-12 shallow Doctor | repository + installed Host/Zone/Project/receipt/OS contract checks; `--full` used in remote readback | VERIFIED locally; external providers separate |
| P2 duplicate sources | one canonical editable OS tree under `os/`; generated distributions are artifacts | VERIFIED structurally |
| P2 CI shape-only | security, contract, compiler, provider-boundary, temp-root install and Factory tests | VERIFIED locally |
| P2 Linux over-broad | scope explicitly Ubuntu/Debian + systemd + apt | FIXED |
| P2 hygiene | cache/symlink scans + release inventory | VERIFIED locally |
| P2 FHS mixed | `/etc` desired, `/opt` immutable software, `/var/lib` observed/runtime, `/srv` human projection | FIXED |

## External gates intentionally not simulated

The repository package is final for milestone 11.12, but `OPERATIONAL` remains evidence-gated. Fresh-VPS reboot, real Hermes mission, Discord test-guild readback, Composio OAuth/MCP, live rootless negative tests, remote drift/rollback and destructive off-host restore must be observed on target infrastructure.
