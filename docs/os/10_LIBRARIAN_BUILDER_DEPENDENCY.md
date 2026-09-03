# Librarian dependency for Builder OS

Librarian is a mandatory upstream capability for Builder. Builder may not substitute ungrounded model recall for the mandatory domain-source handoff.

Required interface:

```text
request: /book --deep --context <context> <theme>
result: sourced research artifact
builder output: 14_BUILDER_HANDOFF.md with 15 selected inputs
```

The Librarian implementation may evolve independently, but the handoff schema and provenance requirements are part of the Builder contract.
