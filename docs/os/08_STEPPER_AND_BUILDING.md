# From an idea to a working OS or product

Stepper is part of the delivered Station system, not a downloaded add-on. Its
canonical source is `os/stepper`. Hermes executes its three profiles and four
native skills; Station supplies ownership, installation and evidence.

## Who does what?

| OS | Director/team | Responsibility | Output |
| --- | --- | --- | --- |
| Stepper | Map Steward, Shaper, Sequencer | Understand the journey, choose a thin end-to-end slice, shape a bet, order releases | Typed story map, slice, pitch and sequence |
| Librarian | Its own installed research team | Check sources, assumptions, contradictions and domain knowledge | Evidence-backed research handoff |
| Builder | Master OS Builder and its specialist team | Build a reusable **OS package**, with its domain contracts, skills, programs and evaluation | Canonical package ready for instance installation |
| DevOps | Atlas, Architect, Forge, Sentinel, Release Engineer, SRE | Build and verify **project software**, integrations and delivery | Tested change, readback and recovery evidence |

Stepper does not replace Builder or DevOps. Building an app usually goes from
Stepper to DevOps; designing a new reusable operational department goes from
Stepper and Librarian to Builder. Research and independent review can run in
parallel where their inputs and owned files allow it.

```text
Your request, admitted by the selected chat/CLI identity
    ↓
Hermes resolves the owning client → Zone → OS instance
    ↓
Stepper: journey → smallest useful slice → shaped bet → release order
    ├── Librarian: verify uncertain domain inputs
    ├── Builder: construct a reusable OS, when that is the requested product
    └── DevOps: implement and test the selected Project, when building software
    ↓
Independent checks → artifacts/readback → human-visible result
```

This is a routing contract, not automatic permission to cross clients. OS
instances and Projects remain siblings under the owning Zone; neither is the
container of the client. Hermes uses the installed `role_profile_map`, not a
guessed bare role such as `master-os-builder` from another instance.

## Installation and first use

Fresh full/core Host bootstrap prepares `stepper`, `builder` and `librarian`
instances in its existing Factory `os` Zone after kernel readback, before the
aggregate optional dependency stage. Team bootstrap selects its exact declared
Organization Zone. It never invents another client Zone or copies credentials.
Other Host roles still carry the canonical source packages; they need an explicit
owning instance instead of an invented Factory.

For an existing reviewed Host release, inspect the targeted default-team plan:

```bash
sudo station os defaults --plan
sudo station os defaults
station os resolve --name stepper
sudo station os resolve --name builder --zone os --instance builder
sudo station os resolve --name stepper --zone os --instance stepper
sudo station os instance chat --zone os --instance stepper --plan
# After enrolling this instance's model:
sudo station os instance chat --zone os --instance stepper
```

`resolve` is read-only. With no Zone/instance it identifies the package and roles,
not an installed runtime. With both, it reads the trusted instance and complete
native team before returning exact routing. Existing default instances are
preserved, not force-reinstalled or silently upgraded. For another Zone, use
`station os instance install` with explicit ownership and an instance ID.

On personal macOS/Linux Workstation, npm installation compiles and installs
the same three teams under the selected `station` root:

```text
station/
├── resources/os-distributions/<os-id>/   generated, replaceable software
├── personal/os/<os-id>/workspace/        your OS-owned artifacts
└── personal/home/os/<os-id>/hermes/      native profiles and private state
```

These are separate Hermes namespaces under your existing Unix user, **not
Linux Zones or client isolation**. Installation does not adopt the real account's
Hermes, browser, GitHub or model-provider credentials. Update preserves enrolled
OS profiles and reports separately when their version needs reviewed migration.

The personal installer also creates `station/bin/stepper`, `station/bin/builder`
and `station/bin/librarian`. Each launcher selects its own native Director and
workspace. For example, `./station/bin/stepper setup model` enrolls that Director;
`./station/bin/stepper chat` uses it. The generic `station/bin/hermes` launcher
continues to select the main personal profile; it does not silently switch OS.

## Who can use Stepper or Builder?

The package is available to the installation. Execution depends on the selected
owner and entry point:

- A local operator uses their existing authorized Host/Zone or personal context.
- A Discord/Telegram/Slack user must be admitted by that gateway's configured
  human/channel policy. A display name, package name or model statement never
  creates membership.
- The Director delegates to the mapped specialists within its instance. A peer
  OS requires an explicitly selected matching scope; otherwise produce a handoff
  artifact and continue useful independent work.
- Destructive actions and production changes need their applicable authority;
  ordinary authorized reversible artifact work proceeds autonomously.

No bot application or Discord token is minted by installation. Configure the
selected Director through `station os instance setup` and `station platform
setup --instance`, then verify/install/start its gateway and test a real message.
Do not enter another instance's token to avoid enrollment.

The legacy AGK specialist `master-os-builder` is a separate same-operator
convenience route. The `agk-station` account naming mismatch is repaired in the
registry, controller and delivered manifest. This does not turn that legacy
session into a client-owned canonical OS instance.

## What is actually verified?

Stepper includes four strict input/output schema pairs, two workflow contracts,
positive/negative fixtures and a deterministic read-only validator. Each native
profile receives these real assets. Validation catches malformed artifacts,
missing journey coverage and inconsistent/cyclic release dependencies. It does
not prove model quality, book accuracy, user acceptance or live integrations.

The archive's 49 bibliographic entries and 150 practices are retained as reported
research inputs, not independently verified knowledge. Its unavailable external
adapters are not relabeled as working connectors. Archive hash and adaptation
mapping are in `os/stepper/provenance/IMPORT.json`.

Every new compiled OS profile receives the shared native orchestration skill and
reviewed turn/concurrency defaults. Every DevOps role additionally receives
`os/devops/prompts/FEATURE_AUDIT.md` in its **SOUL**, requiring inventory,
real user-journey tests, correction, regression checks and honest evidence.
Existing enrolled teams are not silently overwritten by a software update.

See the [fifteen-capability Hermes map](../hermes/16_CAPABILITY_LADDER.md) for
supported commands, native configuration and explicit remaining acceptance gates.
