# Hermes model inheritance for persistent OS instances

## Objective and verified starting point

The user requests that Builder and Stepper use the existing Hermes model instead
of repeatedly asking which provider to configure. On the inspected Host, the
operator Hermes default is `gpt-6-astra` through `openai-codex`. Moonbasecapital's
`moonbasecapital-dev` Zone owns Builder 11.14 (11 roles) and Stepper 0.2.0 (3 roles).
Their native installation is locally verified, but model enrollment is absent.
The configured operator default is not proof of an in-flight `/model` override.

Pinned Hermes already inherits the live provider in transient `delegate_task`
children. Persistent cross-UID profiles do not have that parent object. Reusing
the operator HERMES_HOME would mix runtime state; copying its OAuth store would
introduce credential/refresh ownership conflicts. Neither is the requested fix.

## Plan First and ownership

```text
verified source/default + target Zone/instance identities
  -> inference-only source-owned broker, no agent/session/tool execution
  -> explicit Zone inference grant, separate local capability bearer
  -> native named custom provider in unconfigured target profiles
  -> preserve explicit profile overrides and all non-model state
  -> fake-upstream streaming/negative tests + independent security review
  -> native text/tool roundtrip + target profile/identity readback
  -> immutable release, CI and narrow existing-Host deployment
```

Main owns enrollment, CLI integration, policy/docs, release and Host acceptance.
A worker owns the bounded broker/runtime and its transport tests; a separate
reviewer owns verification of the cross-identity and credential boundaries.
Canonical work stays in the declared Station checkout. OS package definitions
remain provider-neutral; no immutable installed package is force-replaced.

## Scope and acceptance

- The current user instruction authorizes reuse of the operator's inference
  capability for these Moonbase development OSs; it does not authorize copying
  tool accounts, Discord tokens, OAuth stores, sessions, files or client memory.
- Model access sharing is represented by an explicit root-owned Zone grant.
  It is not an implicit grant to every client or production environment.
- Source OAuth resolution and rotation remain under its existing operator UID.
  Targets keep their Zone UID, instance HERMES_HOME, role and workspace.
- Only inference is proxied. The Hermes agent API is not an inference endpoint:
  using it would create an extra agent with the wrong tools/memory.
- Native named custom provider transport must be verified against pinned Hermes;
  a bare custom provider does not select the Codex Responses adapter on loopback.
- No provider secret appears in argv, HTTP errors, logs, evidence or target files.
  A target-local capability token never reaches the upstream provider.
- Explicit target model/provider choices are preserved. Source defaults are used
  when no target override exists. Reconfiguration remains an explicit option.
- Tests must cover authentication, denied routes, streaming, tool call/output,
  source failures/rotation, unchanged profile state and no secret disclosure.
- No six-OS build, gateway restart or live capability acceptance is inferred from
  configuration. External authentication failures remain accurately reported.

## OpenAI integration boundary

Official OpenAI documentation distinguishes ChatGPT subscription authentication
from API-key authentication: <https://learn.chatgpt.com/docs/auth>.
This installation uses pinned Hermes's Codex subscription adapter, not an
invented OpenAI API key. Broker compatibility with that adapter requires separate
native acceptance; the OpenAI documentation does not certify this Station design.

## Native preflight findings

The initial 11.36 Host candidate exposed an ancestry bug in the new capability
helper: Zone users can traverse `0711` Station parents but cannot list them.
The corrected 11.37 helper uses Linux `O_PATH` for ancestors and a readable
descriptor only for its own directory. Native readback as Moonbase's Zone UID
passed without relaxing parent permissions. The six reviewed historical cache/
lock modes were normalized; the resulting preflight checked 35,661 source/runtime
entries and 1,054 confined links. Nested web `node_modules` remain outside Python
import roots, while redirects into them are rejected. The managed base Python's
exact setuptools startup shim is explicitly recognized.

Local baseline verification before that final ancestry patch: 2,577 Station/
Factory tests passed (23 platform-specific skips), 529 AGK component tests passed
(2 unavailable library skips), 263 npm tests passed, and packed-consumer install
verification passed. Final ancestry and release checks must run again, followed
by real model acceptance; these baseline counts alone do not prove live inference.
