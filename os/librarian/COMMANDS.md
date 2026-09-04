# Librarian OS — Command Reference

This release preserves the recovered FULL `/book` interface and restores the dedicated Librarian v8 compatibility commands discussed previously.

## Primary `/book` interface

`/book [flags] <book, subject, question, corpus, or authorized document>`

Core flags:
- `--deep` — deep mechanisms, evidence, alternatives, applications
- `--scholar` — academic evidence protocol
- `--systematic` — bounded systematic-review protocol
- `--apply --context "..."` — application to a concrete context
- `--compare` — common-criteria comparison
- `--synthesize` — cross-source synthesis
- `--critique` — counter-evidence and limitations
- `--quiz` — retrieval/transfer questions
- `--teachback` — explanation + correction loop
- `--cards` — claim-linked learning cards
- `--map` — concept/evidence graph
- `--reading-path` — prerequisite-aware learning path
- `--bestseller` — original editorial/pedagogical book-construction mode
- `--corpus` — multi-source corpus mode
- `--full` — preserve all applicable completeness requirements
- `--refresh` — reassess an existing dossier
- `--language fr|en` — output language

Examples:
```text
/book --deep "Thinking in Systems"
/book --scholar --deep "What evidence supports deliberate practice?"
/book --corpus --compare --synthesize <authorized corpus>
/book --reading-path --quiz --teachback --cards "systems thinking"
/book --deep --apply --map --context "AGK" "multi-agent orchestration"
/book --deep --bestseller --critique "Build an original pedagogical book from this brief"
```

## Dedicated Librarian discovery / verification commands

### `/bestseller <domain>`
Discover and curate a high-value book canon. Bestseller status is evidence-tagged and is never treated as proof of truth.

Recommended full discovery:
```text
/bestseller <domain> --map --global --foundational --current --practical --contrarian
```

### `/web-deep <question>`
Deep web/source investigation for current, primary, official, technical, practitioner and failure evidence.

### `/experts <domain>`
Map credible experts, schools of thought, practitioner voices and relevant dissenters. Authority is scored; fame is not evidence.

### `/contrarian <domain-or-claim>`
Actively seek opposing schools, failure cases, boundary conditions and counter-evidence.

### `/sources <claim-or-domain>`
Produce the source ledger: provenance, access level, quality, recency, independence and applicability.

### `/verify-source <source-or-claim>`
Verify identity, provenance, date, access, relevance and whether the source actually supports the attributed claim.

### `/principles <dossier-or-domain>`
Compile validated principles, mechanisms, decision rules, contextual conditions and confidence.

### `/contradictions <dossier-or-domain>`
Surface unresolved conflicts; do not average them away. Produce school map, contradiction register and contextual resolution rules.

### `/best-inputs <goal>`
Select the smallest high-value, non-redundant input corpus needed for the goal using coverage and saturation rather than arbitrary source counts.

### `/handoff <verified-dossier>`
Package validated research for the next OS: requirements, assumptions, claims, tests, open decisions, evidence links and explicit gates.

## Administration

`/librarian <action> <target>`

Actions recovered from FULL:
`inbox`, `search`, `status`, `audit`, `graph`, `refresh`, `cards`, `export`.

## Important semantic distinction

There are two different “bestseller” concepts:
1. `/bestseller <domain>` = discovery and curation of commercially influential / canonical books with evidence labels.
2. `/book --bestseller ...` = creation of an **original** editorial/pedagogical structure. It does not guarantee sales and does not imitate or reproduce protected books.


# v3 Universal Knowledge Commands

### `/research <question>`
Universal research router over every available source class.

Useful modes:
```text
/research <question> --deep --current --primary --scholar --web --books --community --contrarian
```

### `/web-deep <question> --recursive`
Search, read, follow citations, deduplicate, challenge, and synthesize current internet knowledge.

### `/prior <domain-or-question>`
Generate model-prior hypotheses. Output is explicitly unverified and cannot be promoted directly.

### `/prior-verify <domain-or-question>`
Generate model priors, atomize claims, then attempt external validation.

### `/discover <domain>`
Discover vocabulary, entities, experts, sources, books, repositories, communities, datasets and schools before deep research.

### `/canonical <domain>`
Find the strongest foundational / authoritative sources, not merely the most popular.

### `/latest <domain-or-claim>`
Freshness-focused research. Prefer dated primary/official sources and produce a change log relative to durable knowledge.

### `/papers <question>`
Scholarly discovery and evidence mapping.

### `/docs <technology-or-system>`
Prioritize current official technical documentation and version-specific evidence.

### `/github <topic>`
Use repositories, releases, code, issues and discussions as engineering evidence when available.

### `/community <question>`
Mine practitioner/community experience while preserving anecdotal status and source independence.

### `/triangulate <claim>`
Attempt to validate a claim across genuinely independent source classes.

### `/factcheck <claim>`
Trace the claim upstream and issue a verdict with provenance and uncertainty.

### `/knowledge-gap <domain>`
Show what the Librarian still does not know, what is stale, contradictory or weakly sourced.

### `/refresh-knowledge <domain>`
Re-run freshness-sensitive claims and generate source/claim/logic diffs.

### `/research-to-os <domain>`
Create a Builder-ready verified knowledge package from universal research.
