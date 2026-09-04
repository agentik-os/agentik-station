# Dedicated AGK Station Linux account

The recommended installation never develops from `/root`. The first bootstrap creates a dedicated interactive automation account:

```text
agk-station
```

Its home is intentionally small and predictable:

```text
/home/agk-station/
├── repos/agentik-station/
├── .hermes/
├── .local/bin/
├── .local/share/npm/
└── .config/
```

Hermes and Codex are installed for this account. Station operational state itself continues to follow FHS under `/etc/station`, `/opt/station`, `/srv/station`, `/var/lib/station`, `/var/log/station`, `/var/backups/station`, and `/run/station`.

For autonomous coding-agent bootstrap, `agk-station` may receive passwordless sudo. This is explicit in `bootstrap.sh --sudo-mode passwordless`; environments requiring interactive sudo can choose `--sudo-mode password`.

The bootstrap refuses to run from a repository checkout under `/root`; use `/tmp/agentik-station` for the one-time source checkout.
