# Ponytail — required integration, blocked delivery

Ponytail remains required in Station's engineering integration plan, but is
**NOT_INSTALLED** on the reviewed Host. The retained native Hermes security scan
rejected the pinned v4.9.0 source. Its commands and modes are unavailable.

Repository maturity is **SCAFFOLDED**, not `INSTALLABLE` or `DEGRADED`: delivery
is blocked, not a failure of a previously configured Ponytail runtime. Declaring
it in the full software selection or OS policy is not installation evidence.

Repair requires an upstream-reviewed scanner correction or published plugin
distribution, a reviewed immutable pin, the full native security scan, and then
scoped runtime/command/ACL acceptance. Preserve the guard: do not filter the
source, manually copy the plugin, add a trust exception or bypass scanning.
Retrying the retained blocked pin is not a repair.

Independent engineering work can continue with Station's existing reviewed
reuse, validation and evidence guidance. This is not an installed replacement
for Ponytail; Ponytail-dependent acceptance remains outstanding.

See the [native scan evidence](../../docs/audit/2026-09-05-ponytail-native-scan.md)
and [intended engineering role](../../docs/hermes/12_PONYTAIL_ENGINEERING.md).
