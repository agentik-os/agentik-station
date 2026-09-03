# Capability Contracts and Adapter Resolution

AGK defines **capabilities**, not a flat bag of tools.

```text
profile + mission + environment
        ↓
Station Context Envelope
        ↓
AGK capability contract
        ↓
policy / approvals / budget
        ↓
adapter compiler
        ↓
Hermes native | MCP/plugin | Composio | direct API | deterministic program
```

The adapter is an implementation detail. An OS asks for `gmail.send`, not “give me Composio”. It asks for `github.pr.create`, not “give me all GitHub tools”.

Capability contracts declare:
- operation semantics;
- read/write/destructive risk;
- allowed environments;
- required approvals;
- identity/connected-account scope;
- evidence requirements;
- adapter constraints;
- budgets/rate limits when needed.

An OS may tighten policy, never silently weaken mandatory Station governance.
