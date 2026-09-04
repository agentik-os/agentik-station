# Imported Builder/Librarian Pack Integration

The user-supplied `AGK_Builder_Librarian_OS_COMPLETE_2026-09-03` is included **intact** under `98_SOURCE_PACKS/` for provenance/recovery.

Station v6 also activates normalized copies:

```text
17_RUNTIME_OS_PACKAGES/builder-os
17_RUNTIME_OS_PACKAGES/librarian-os
17_RUNTIME_OS_PACKAGES/_os-template
16_OS_FACTORY_INTEGRATION/schemas
16_OS_FACTORY_INTEGRATION/workflows
16_OS_FACTORY_INTEGRATION/programs
16_OS_FACTORY_INTEGRATION/tests
```

## Normalizations applied only to active copies

1. thread semantics: thread = Hermes session surface, Mission/Kanban = durable source of truth;
2. AGK Context/Capability Router is not a second execution engine; desired state compiles to Hermes config/tools/hooks plus Station policy enforcement;
3. Station context envelope and trust-zone requirement added;
4. Builder code capability inherits Engineering Constitution;
5. Hermes update compatibility is owned by Station Maintainer;
6. source pack remains unchanged so its original provenance remains inspectable in the preserved audit/history materials.
