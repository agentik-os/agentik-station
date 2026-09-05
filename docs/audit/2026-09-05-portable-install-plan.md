# Plan First — portable Station installation

## Mission and constraints

Provide a branded, dependency-free npm entry point for an explicitly reviewed,
non-root macOS/Linux Workstation installation. Preserve the canonical Linux Host
installer and its independent-UID Zones. A Workstation is a personal namespace,
not a Zone, security sandbox, client isolation boundary or operational OS fleet.
Do not reset hosts, adopt personal Hermes/CLI credentials, edit shell startup
files, publish npm credentials, activate gateways or terminate existing sessions.

The requested workspace is this repository. Existing release 11.25 is clean on
main. Available executors: Node 22, npm, uv, Cargo, Git, local macOS; Linux CI and
the existing VPS remain available for scoped verification. Native Hermes is
pinned by config/versions.lock. Native macOS gateway install also starts launchd;
it must therefore be treated as explicit activation, never a staging operation.

## Dependency graph and ownership

```text
A context / safe filesystem / npm CLI (root; verify: runtime owner)
├── B pinned portable runtime + AGK staging (runtime owner; verify: root)
├── C scoped Hermes gateway + truthful checks (gateway owner; verify: root)
└── D terminal presentation + accessibility (presentation owner; verify: root)
    A+B+C+D → E package/native smoke + adversarial tests (root; verify: CI)
            → F documentation / release inventory / main (root; verify: CI)
```

Shared ESM interface: context has absolute `root`, `sourceRoot`, `home`, `tools`,
`bin`, `cache`, `evidence`, `resources`, `projects`, `hermesHome`, `profile`, plus
`platform`, `arch`, and `pins`. Runtime owns `installer/npm/runtime.mjs` and its
tests; exports `provision(ctx, {run, emit})` and `verify(ctx, {run, emit})`.
Gateway owns `installer/npm/gateway.mjs` and tests; exports
`gateway(ctx, action, {run, interactive})` (configure/model/status/activate).
Presentation owns `installer/npm/ui.mjs` and tests; exports `createUI` with
`banner`, `plan`, `event`, `summary`, `close`. Root owns all remaining new files,
documentation, packaging, CI and coordinated release metadata.

Implementation extensions within this mission: the gateway owner also owns
`connectors.mjs` and its tests (pinned GitHub/Composio native artifacts); the
presentation owner owns `onboarding.mjs` and tests (explicit interactive
continuation). Root owns portable `web.mjs` and the web-root adapter. The runtime
owner owns the shared Workstation context helper and AGK/plugin path adapters.
Root verifies all branches. A confirmed upstream macOS Composio signature defect
is handled only as a disclosed derived-artifact transformation for one reviewed
version/digest; original bytes and transformation evidence must survive, no
system security controls may be disabled.

`run(executable, argv, options)` is asynchronous, shell-free, bounded and returns
`{code, stdout, stderr}`; failures throw by default, `allowFailure` returns the
failure. `options` supports `cwd`, `env`, `timeoutMs`, `interactive`. Commands
use an explicit private HOME and caches; tokens are neither argv nor receipts.
Events are `{phase, status, message}`; verification checks are
`{id, status, detail}`. Status distinguishes verified, blocked, failed, and
not-configured. Copying software is never live-service acceptance.

## Acceptance and failure handling

- No npm lifecycle installation hooks; package install alone cannot change OS.
- Explicit review before writes; occupied/unmanaged/symlink roots fail closed.
- All managed dependencies, caches, source and evidence stay under chosen root;
  native launchd's required account-home plist is disclosed at activation.
- Pin source/dependencies; require missing platform prerequisites explicitly.
- Stage complete AGK support files, test normal usernames and private runtime.
- Test CLI help/plan, plain and animated rendering, package tarball, safe paths,
  failure receipts and explicit repair; never claim failed/skipped tools ready.
- Verify real Hermes revision/imports, AGK/RMUX and plugin discovery where
  executable; expose accounts, hardware, Linux-only and service gates honestly.
- No model purchase, Discord messages, token extraction, gateway activation,
  sudo package changes or npm publication in synthetic/native acceptance.
- Relevant tests, repository Doctor, metadata, package smoke and CI must pass.

Failures preserve receipts. Repair is an explicit command, limited to owned
software; it does not erase credentials, configuration, projects or prior
evidence. macOS native acceptance and Linux CI acceptance are separate claims.
