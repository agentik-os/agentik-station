# Hermes Capability Diff

Every detected upstream change gets classified by Station Maintainer.

| Class | Meaning | Station action |
|---|---|---|
| `native_replacement` | Hermes now provides a custom Station feature | migrate then delete custom code |
| `native_extension` | Hermes adds useful primitive | integrate behind AGK contract |
| `schema_change` | config/API/hook changed | update compiler/tests |
| `behavior_change` | existing semantics changed | regression + policy review |
| `security_change` | permissions/sandbox/update behavior changed | Security reviewer mandatory |
| `no_action` | irrelevant to Station | record and close |

Ponytail principle applies to infrastructure: **the best Station module is the one Hermes made unnecessary.**
