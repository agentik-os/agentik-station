# Model-Agnostic Builder

Builder OS must not depend semantically on one vendor or model name.

## Logical roles

Example roles:

- `builder-director`
- `domain-research`
- `coding-worker`
- `independent-review`
- `security-review`
- `fast-classifier`

The Node resolves each role to a Hermes provider/model configuration from the pinned environment.

Per-task overrides may be used for quality-sensitive Kanban cards. Fallbacks must preserve capability requirements (tool use, context, structured output) rather than blindly substituting any available model.

## Drift detected in current public Builder config

The existing `config.yaml` and `distribution.yaml` use different primary model/provider stories. Treat distribution metadata as compatibility/default intent and compile runtime routing from one canonical AGK provider-route policy to prevent drift.
