# Use Hermes's model in Builder and Stepper

Persistent OS instances retain separate Hermes homes. They do not inherit the
in-memory provider of the session that created them. A native `delegate_task`
child does; an independently installed Director does not.

Station can give an explicitly selected Zone **inference access**, without
copying the operator's OAuth, memory, chat history or tool accounts:

```text
Builder / Stepper role (its own Zone UID, memory, tools, workspace)
    -> named native provider custom:station-inference
    -> localhost:8791, Zone-local capability
    -> source-owned inference transport
    -> operator Hermes's persisted default model and existing OAuth

Model tool calls -> returned to the OS -> executed by that OS, not the operator
```

## Operator setup — once for the intended client Zone

From an installed immutable Linux Host release:

```sh
sudo station model enable --plan
sudo station model enable
sudo station model grant --zone moonbasecapital-dev --instance builder --instance stepper --plan
sudo station model grant --zone moonbasecapital-dev --instance builder --instance stepper
sudo station os instance verify --zone moonbasecapital-dev --instance builder
sudo station os instance verify --zone moonbasecapital-dev --instance stepper
```

The grant enrolls the entire declared teams, not just their Directors. On later
`station os instance chat` or `setup`, an unconfigured granted role automatically
uses `hermes-default`. A role with an explicit model/provider/endpoint keeps its
choice. `setup --choose-provider` explicitly opens native provider selection.
No user should be asked to choose a provider merely because a new role has no
local model, when its valid inherited route is already available.

Enrollment reports native route readback, **not successful provider inference**.
Verify the OS teams again, then test a fresh model response and a local function
tool roundtrip. An already-open provider wizard is not a new session; leave that
wizard and reopen the instance after enrollment. Do not copy credentials to fix
it, and do not claim unrelated mission builds started.

## Boundaries and supported transport

- Initial implementation: pinned Hermes Codex Responses transport, operator
  `agk-station` at `/home/agk-station/.hermes`, Linux Host/systemd. This is not yet
  a universal provider or macOS relay. Unsupported source providers fail clearly.
- `hermes-default` follows the operator's **persisted configuration**, not an
  ephemeral `/model` override in a different active chat.
- The source uses its existing ChatGPT/Codex subscription authentication, not an
  invented OpenAI API key. These are distinct authentication methods in the
  [OpenAI documentation](https://learn.chatgpt.com/docs/auth). Compatibility of
  this relay is verified against pinned Hermes, not certified by OpenAI.
- The current adapter validates the exact Hermes Git pin. A tarball-only Hermes
  install needs a future trusted source-receipt adapter; it is not silently
  treated as a validated checkout. No automatic model/provider upgrades.
- Source native code remains source-operator-owned. Activation validates source,
  interpreter and dependency trees; this does not make them immutable against
  that same operator. Root-controlled Station code runs the broker as the source
  UID with `NoNewPrivileges`, never importing Hermes into a root process.
  Activation can normalize only six reviewed historical lock/cache permissions
  (empty locks `0600`, four cache directories `0755`); unexpected entries fail
  validation and no recursive permission rewrite is performed.
- HTTP bearer possession grants inference; TCP does not prove Unix UID. Roles
  sharing the Zone UID share that capability. The instance list controls
  enrollment, not per-instance kernel isolation. Other clients get no grant.
- Only inference is exposed. No provider account, source agent, file, session,
  browser, provider-hosted tool or conversation-state endpoint is proxied.
  Requests use explicit context and `store: false`. OAuth stays source-owned.
- Source/grant configuration is root-owned, readable only by the source group.
  Enrollment bindings are root-only. The target bearer is Zone-owned `0600` and
  native `key_cmd` reads it without an API key in YAML or command arguments.
- Model requests consume the source account's quota. Request/concurrency/time
  limits exist; a monetary budget or per-client billing meter is **not** provided.
  Provider limits and unavailable authentication remain real failure conditions.

## Recovery, revocation and updates

```sh
sudo station model revoke --zone moonbasecapital-dev
```

Revocation removes network authorization before updating enrollment metadata;
broken metadata cannot keep the grant active. Previously accepted streams may
finish. Target tokens/config remain recoverable, but no longer grant inference.
Granting the same verified scope again reuses its existing local capability.
Conflicting local credentials are never silently adopted or replaced.

After installing a new immutable Station release, run `station model enable
--plan` and `station model enable` to update the inference-only service from its
recognized prior frozen implementation. This may restart **that transport**;
it does not restart Discord/Hermes gateways. A custom modified unit is preserved
for explicit review. Read the profile outcomes after any partial enrollment:
independent roles continue, failures are `INCOMPLETE`, and configuration alone
never establishes `OPERATIONAL`.
