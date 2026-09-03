# Self-Improving Agents with Governance

Hermes already includes a closed learning loop: curated memory, autonomous skill creation/improvement, cross-session recall and background self-improvement review.

Agentik does not rebuild this. It adds governance around what may be learned and promoted.

## Learning pipeline

```text
Mission outcome
   ↓
Hermes background review
   ↓
Candidate memory / skill patch
   ↓
Risk classification
   ├── low-risk personal workflow → may auto-apply
   ├── shared engineering skill → eval + review
   └── policy/security/capability → human approval required
   ↓
Evaluation
   ↓
Promote / Reject / Quarantine
   ↓
Versioned skill distribution if reusable
```

## Never self-modify automatically

The learning loop MUST NOT autonomously weaken or rewrite:
- authentication/authorization policies,
- client boundaries,
- secret scopes,
- production approval gates,
- security controls,
- backup/restore policy,
- evidence requirements,
- model cost ceilings beyond configured policy,
- OS licensing/governance rules.

## Production recommendation

Use approval/staging for writes that affect shared skills. A lesson learned by one mission becomes a candidate, not instantly a company-wide truth.

## Skill lifecycle

```text
observation
→ candidate lesson
→ candidate skill patch
→ replay/eval cases
→ independent review
→ version bump
→ candidate channel
→ stable channel
```
