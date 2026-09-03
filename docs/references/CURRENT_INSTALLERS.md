# Current upstream installer assumptions (2026-09-03)

Station uses upstream-supported installation paths rather than vendoring third-party runtime binaries.

## Hermes Agent

Official Linux CLI installer:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

For Station root/FHS installation the installer is invoked non-interactively with setup deferred:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
  | bash -s -- --skip-setup --non-interactive \
      --hermes-home /var/lib/station/hermes-bootstrap
```

The upstream installer supports an FHS-style root Linux install with code under `/usr/local/lib/hermes-agent` and the `hermes` command under `/usr/local/bin`; mutable Zone state must still use explicit Zone-scoped `HERMES_HOME` paths.

Hermes updates are checked by Station but promoted through Station release rings rather than blindly pushed to every client environment.

## Composio CLI

Official installer:

```bash
curl -fsSL https://composio.dev/install | sh
```

Station overrides install/bin locations and skips shell rc modification:

```bash
curl -fsSL https://composio.dev/install \
  | COMPOSIO_INSTALL_DIR=/opt/station/tools/composio \
    COMPOSIO_BIN_DIR=/usr/local/bin \
    COMPOSIO_INSTALL_SHELL=none sh
```

Composio login, connected accounts and principal bindings remain setup-time operations; they are never embedded in the Station repository.
