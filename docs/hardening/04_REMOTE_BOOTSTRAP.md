# Hardened Remote Bootstrap

v11 remote bootstrap is a secure transport primitive, not the final Fleet system.

It validates target/user/port, uses strict host-key checking by default, creates a private operation directory, transfers a normalized release archive and a separate JSON InstallSpec, invokes fixed executable paths, and reads reported Station status.

Desired identifiers never become fragments of a reconstructed remote command.

Still required for Fleet maturity:

- authenticated Station Node Agent;
- signed/versioned desired-state reconciliation;
- operation identity and replay safety;
- remote receipt ingestion;
- drift detection;
- remote rollback and recovery;
- Tailscale identity attestation;
- accepted health/readback evidence.
