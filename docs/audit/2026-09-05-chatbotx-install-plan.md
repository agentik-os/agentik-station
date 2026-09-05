# Plan First — ChatbotX installation and npm distribution

## Mission and boundary

Add the reviewed ChatbotX client capability to the default Station Workstation
and Linux Host installation. Hermes remains the execution orchestrator and
Station's human messaging gateway; ChatbotX is an explicitly connected marketing
application, not a replacement Station control plane or a second Discord admin.
The owning development workspace is this repository on `main`, initially clean
at `8a1223a3a22aec99a0b1b004fc7d46a6ba7c153f`. The candidate release is 11.27.

Inspect the upstream CLI, MCP and self-hosting contracts before selecting the
smallest supported integration. Pin reviewed code and package integrity. Install
software without enrolling an account, starting a public server, sending a
message, provisioning a database or adopting personal credentials. Self-hosted
application deployment and cloud account setup remain explicit acceptance gates.
Do not install a guessed or unpublished npm package. Any MCP launch must use
stdio explicitly rather than accepting an upstream HTTP listener default.

The user requested npm publication. A credential pasted in chat is treated as
exposed: it will not be copied into a tool call, file, repository or receipt.
The existing local npm identity probe returned HTTP 401. Publication requires
fresh official authentication or an already configured trusted publisher; no
registry ownership or successful publication is assumed.

## Execution graph and owners

```text
A source and architecture review (root; verify: upstream reviewer)
├── B upstream CLI/MCP/deployment review (upstream reviewer; verify: root)
├── C Host/default-install extension map (explorer; verify: root)
└── D release/resource/security contracts (root; verify: tests + reviewers)
    B+C+D → E scoped implementation (assigned file owners; verify: root)
          → F native offline capability acceptance + regressions (root + CI)
          → G metadata / docs / main / CI readback (root)
          → H npm publication (only with valid scoped authentication)
```

Mutable ownership will be explicitly assigned before parallel implementation.
Workers must preserve each other's changes. Existing accounts, production VPS
state, client OS instances and Hermes profiles are outside mutation scope.

## Acceptance

- The default installer actually installs the supported pinned client software;
  a catalog entry or downloaded source alone is not native acceptance.
- Native CLI version/help, package integrity and complete support-file checks
  work with disposable private HOME/cache and no account or network mutation.
- If supported MCP can be built or installed, exercise initialize/tools discovery
  over stdio without real credentials; expose unavailable upstream pieces honestly.
- Never auto-enable external account tools in every client/Zone/profile.
- Preserve Workstation private paths and Host root-owned shared-code publication.
- Add failure, isolation and package-contract regressions; test npm consumer
  tarball and relevant Host/AGK contracts; run Doctor and deterministic metadata.
- Record exact upstream pins, native evidence and all skipped external gates.
- Push only `main`, verify final CI, and distinguish source publication from npm
  registry publication and live ChatbotX service/account acceptance.
