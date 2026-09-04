# Model Prior Protocol

## Purpose
Exploit useful latent model knowledge without confusing it with verified knowledge.

## Stage 1 — Prior dump
Ask one or multiple available models independently for:
- known concepts;
- likely canonical sources;
- important experts;
- terminology;
- mechanisms;
- disputed claims;
- unknowns;
- likely recent-change areas.

## Stage 2 — Atomize
Turn the prior into atomic claims.

Each record:
- claim
- model/provider
- confidence expressed by model
- expected source class
- search queries
- risk if wrong
- status = UNVERIFIED_MODEL_PRIOR

## Stage 3 — Adversarial prior
Ask a separate reasoning pass:
- What is likely stale?
- What sounds plausible but may be false?
- What sources would disprove this?
- Which claims are likely model-training artifacts?

## Stage 4 — Verify
Run external/authorized research.

Statuses:
- VERIFIED_PRIMARY
- CORROBORATED
- PARTIALLY_SUPPORTED
- DISPUTED
- OUTDATED
- UNVERIFIED
- REFUTED

## Stage 5 — Promote
Only validated claims may enter reusable knowledge.
The original model-prior provenance remains in the audit trail.
