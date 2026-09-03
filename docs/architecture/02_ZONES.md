# Zones

A Zone is the canonical isolation primitive.


Categories:

```text
1_SYSTEM
2_PRIVATE
3_AGENTIK
4_CLIENTS
5_PROJECTS
6_FACTORY
7_LAB
```

The category name is not repeated in the child name. Use `4_CLIENTS/moonbase/dev`, not `4_CLIENTS/moonbase-client/client-dev-zone`.

A Zone has one explicit Host placement and one environment. Remote placement does not change its internal contract.
