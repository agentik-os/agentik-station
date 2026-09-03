# Model-Agnostic Coding

Hermes supports many providers, custom OpenAI-compatible endpoints, per-request model selection, auxiliary models, delegation-specific model overrides and fallback chains. Agentik therefore treats the model as a routing choice, not as workflow identity.

## Rule

**OS behavior MUST be specified in contracts, skills, tests and tool permissions — never depend on one model's undocumented personality or prompt quirks.**

## Role requirements, not model names

Bad:

```yaml
reviewer:
  model: some-vendor-specific-model
```

Canonical:

```yaml
reviewer:
  capability_class: deep_code_review
  requirements:
    tool_calling: true
    long_context: true
    reasoning: high
  route: engineering-review
```

The Node maps `engineering-review` to a current provider/model and may change it without rewriting the OS.

## Model routing layers

```text
OS role requirement
      ↓
AGK route alias
      ↓
Hermes provider:model
      ↓
fallback chain
```

## Suggested routes

```yaml
model_routes:
  engineering-director:
    class: high_reasoning
  coding-worker:
    class: strong_coding
  fast-research:
    class: fast_low_cost
  engineering-review:
    class: independent_high_reasoning
```

## Independence requirement

For high-risk Gauntlet review, prefer a critic route that is independent from the implementer's exact model/provider when economically reasonable. This reduces correlated blind spots but is not a substitute for deterministic verification.
