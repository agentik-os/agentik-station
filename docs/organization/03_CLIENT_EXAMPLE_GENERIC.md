# Example Client Example

This is deliberately different from Operator.

This is a business-domain map, not a filesystem tree. Each deployed capability
becomes a client-owned OS instance in the appropriate development/production Zone;
client Projects are separate work objects that those instances may serve.

```text
Example Client Capital
├── Investment Operations
│   ├── Searchers
│   │   ├── Searcher Intake OS
│   │   ├── Searcher Scoring OS
│   │   ├── Interview OS
│   │   └── Searcher Portfolio OS
│   ├── Dealflow
│   │   ├── Deal Intake OS
│   │   ├── Screening OS
│   │   ├── Research OS
│   │   ├── Financial Analysis OS
│   │   ├── Due Diligence OS
│   │   ├── Investment Memo OS
│   │   └── Investment Committee OS
│   └── Portfolio
│       ├── Monitoring OS
│       └── Reporting OS
├── Fund Operations
│   ├── LP Pipeline OS
│   ├── Fundraising OS
│   ├── Capital Call OS
│   └── Investor Reporting OS
├── Technology
│   ├── Product OS
│   ├── DevOps OS
│   ├── Data OS
│   ├── QA OS
│   └── Security OS
└── Corporate Operations
    ├── Finance OS
    ├── Legal / Compliance OS
    └── Backoffice OS
```

## Important

Generic OSs can be reused:
- DevOps
- Knowledge
- Research
- Decision
- Meeting

Vertical OSs are organization/industry-specific:
- Searcher Scoring
- Investment Committee
- Capital Call

Reuse the **definition**, not another client's configured runtime. Credentials,
connected accounts, databases, memory, sessions and evidence stay with the owning
client environment. The [instance contract](05_OS_INSTANCES.md) describes registration,
Director/team namespacing, private setup and the current implementation boundary.
