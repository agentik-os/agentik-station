# Seven Capability Lanes

## 1. Clarify and Plan

Transforms ambiguity into an executable mission contract.

Outputs:
- explicit objective;
- in-scope / out-of-scope boundaries;
- constraints and assumptions;
- acceptance criteria;
- risk/irreversibility class;
- required capability probes;
- Loop-Graph plan;
- owners and verification owners.

Rule: reversible low-risk ambiguity may proceed with explicit assumptions. Irreversible, security-sensitive, financial, client-boundary or externally visible ambiguity requires an approval/clarification gate.

## 2. Build with Leverage

Before new work, search for leverage in this order:

```text
do nothing / remove requirement
→ existing Station/OS capability
→ existing repo implementation
→ native platform feature
→ deterministic program
→ Hermes native primitive
→ installed dependency
→ MCP / Composio / existing API
→ reusable Skill / OS package
→ only then new implementation
```

Ponytail is the coding-level expression of this lane; Station extends the principle to architecture and operations.

## 3. Research and Learn

Uses Librarian Intelligence: topic map, canonical books, web-deep, experts/operators, source verification, freshness, contradictions, failures/contrarian evidence and editorial synthesis.

Research outputs must distinguish:
- sourced fact;
- current observation;
- expert opinion;
- synthesized principle;
- uncertain hypothesis.

## 4. Code and Ship Safely

Executor-neutral. Hermes, Codex, Claude Code or another declared executor may own implementation.

Claims are gated:

```text
prepared handoff != code executed
executor running != code correct
executor reported done != tests passed
tests passed != review passed
review passed != CI passed
CI passed != deployed
deployed != healthy/read back
```

## 5. Create Polished Deliverables

Applies to websites, visual assets, reports, decks, PDFs, posters and other user-visible artifacts.

Each artifact class declares:
- content acceptance;
- visual/taste criteria;
- render mechanism;
- render inspection gate;
- accessibility/usability checks where relevant;
- final artifact/readback evidence.

No “looks good” claim without rendering or viewing the actual deliverable.

## 6. Remember and Operate

Memory is review-first, not automatic dumping.

After mission completion:
- classify durable lessons;
- reject transient/noisy facts;
- propose memory/Skill updates;
- promote under policy;
- update runbooks/readiness state;
- record next repair action for degraded systems.

## 7. Connect with Clear Boundaries

Before work depends on a tool/connector, probe:
- installed/registered;
- reachable;
- authenticated;
- correct principal/organization;
- intended account;
- allowed tool/capability;
- read/write mode;
- environment;
- approval requirement;
- simple health/readback operation when safe.

A connector described in configuration but unavailable at runtime is **not** an available capability.
