# Stepper OS

Stepper turns a user journey into a story map, a walking skeleton, a shaped bet and an ordered release sequence. It does not build or deploy applications, promise velocity, create accounts, or authorize production work.

Three native Hermes identities: map-steward (Nano Director, maps and slices), shaper (bets), sequencer (release order). Four real skills, strict JSON schemas, two declared workflows and a standard-library validator ship with the package.

## Scope and discovery

The package is stepper-os; map-steward, shaper and sequencer are role labels, not package IDs, logins or authorization grants. Resolve an existing owning Zone and OS instance (or the explicitly enrolled personal Workstation), then use its exact generated role_profile_map. Never select a bare role from another instance. Projects are optional bounded inputs, not the owner of an OS instance. Unknown membership or context blocks access; a display name is not evidence.

On Host use station os catalog, station os resolve --name stepper and station os doctor/compile, then station os instance install/setup in the existing owning Zone; package availability is not instance installation. Resolve an installed instance with explicit --zone and --instance arguments before invoking a role. In Workstation use only its enrolled private root and namespaced profiles, never a Host Zone fiction. A dedicated Director Discord bot/channel is enrolled separately; internal specialists need no extra bots.

## Local verification

Run python3 programs/runner.py validate-package from the canonical package, and python3 programs/runner.py evaluate from either the package or its distributed profile. Run python3 programs/runner.py validate --skill story-map --input examples/story-map.json for a typed artifact. The validator has no network, subprocess, credential, or write capability. It validates supplied work; it does not claim a model produced it or a user accepted it.

## Input-bound validation and Builder handoff

The native skills validate their original input and proposed output together with `transition --skill <id> --input <input.json> --output <output.json>`. This checks actor/journey identity, complete journey coverage, the original problem/outcome, the supplied appetite, and the exact slice inventory/dependencies. Changed wording or scope must be clarified in the original input rather than silently substituted in an output. An unordered acyclic input backlog is valid; cycles, unknown dependencies and duplicate identities are refused. These are deterministic contract checks, not model-behavior scores.

`examples/step-loop-bound.json` includes all four original inputs plus the outputs. From the package directory, `python3 -I -B programs/runner.py handoff --input examples/step-loop-bound.json` produces the typed example in `examples/builder-handoff.json`; `handoff-check --input <handoff.json>` rechecks its contents and hashes. Installed skills use an absolute runner path and workspace-local inputs instead. The handoff envelope is in `data/HANDOFF.schema.json`; the runner separately validates its embedded artifacts against the existing skill schemas and transition rules. Builder consumes this file as a hash-bound input, with its own explicit scope and separate Librarian evidence. No files, workers, accounts or services are created by these commands. Hash validity never means user acceptance, execution authority or verified research.

## Research and provenance

The supplied v0.1.0 ZIP contains 52 text files, 49 bibliographic candidates and 150 structured practices. Useful content is adapted into the canonical package; the original ZIP is not redistributed. See provenance/IMPORT.json and its per-file mapping. Imported assertions of verified books, quality91 and confidenceA are reported claims, not Station verification. No license is invented. Publisher/source checking remains a Librarian task before evidence promotion; no book/PDF text is included.

Librarian replaces the unresolved research-os dependency. Builder's evaluation discipline replaces evaluation-os; Builder builds accepted specifications and DevOps reviews delivery/recovery instead of an absent release-os. These are explicit handoffs to an existing authorized instance, never automatic cross-Zone invocation.
