# Plan First — complete required stack and VPS repair

## Objective and observed baseline

The user requires every requested component to be installed by future VPS
installations and on `moonbase@76.13.36.148`, not merely named in a manifest.
The owning source workspace is `/Users/hacker/agentik-station`, initially clean
on `main` at `17dcd837b832b3a339e948ee87f2cc849d808590`. Candidate release: 11.28.

Read-only SSH with the existing named key verified Host `capital`, Ubuntu/Linux
x86_64, sudo, 32 GiB RAM and approximately 370 GiB available storage. The active
kernel is **11.25**. ChatbotX and Ponytail are absent; Langfuse is a checkout;
Honcho/Hindsight client environments and both web runtimes exist; Parakeet and
the guided-setup broker are active. A Git checkout count is not a capability audit.

Source audit confirmed `--mode full` selects topology, not the full stack:
`INSTALL_AI_STACK=0`. The optional `--all` stops on the first failing component.
Langfuse has no server installation; the two memory installers only install SDKs.
The last 11.27 delivery added ChatbotX's CLI, not its complete application.

## Scope and non-negotiable boundaries

- Make the complete requested Host software inventory explicit and mandatory;
  an omitted, failed, unsupported or security-blocked requirement cannot produce
  a full-install success. Personal Workstation is not an equivalent Linux Host.
- Attempt independent components even when one fails, preserving individual
  failure evidence and a nonzero aggregate result. Never suppress shell errexit
  by wrapping an installer function in a tested conditional.
- Install actual reviewed executables/server images and their support resources,
  not source-only placeholders. Bind installed evidence to exact bytes/digests.
- Keep software installation, service configuration/startup, profile bindings,
  account enrollment and live mission acceptance as separate observable facts.
- No public listeners, upstream demo users, example passwords, database migration
  against existing state, Docker pruning, security-scan bypass or broad Docker
  grants. New service code/images may be installed without executing them.
- Ponytail's native full-tree security rejection remains a real incomplete gate,
  not an exception removed from the required list. No manual plugin copying,
  filtered package or trust override is permitted to evade that decision.
- Preserve existing Zone/instance identities, profiles, credentials, services,
  sessions and immutable releases. Do not rerun full Host bootstrap to fill gaps.
  Use the reviewed new immutable kernel and targeted component installation.
- Provider keys and memory/observability principal bindings must never be guessed
  or copied between profiles. Strix execution remains separately accepted LAB work.
- Do not use the previously exposed npm token; npm publication is outside this
  component-repair mission.

## Execution graph and ownership

```text
root: contracts + live inventory + integration + release/VPS verification
├── installer-map owner: full inventory/orchestration/checker proposal and tests
├── services owner: native memory/observability/VNC/Parakeet service recipes
└── upstream owner: ChatbotX complete software recipe + Ponytail native constraints
      ↓ disjoint implementation ownership confirmed before edits
full-profile defaults → software installation + per-component evidence
      → relevant regression tests + Doctor + independent review
      → immutable main release + CI
      → targeted VPS repair + exact native/read-only readback
      → report every installed / pending / blocked capability without omissions
```

Root is verification owner for each delegated branch. Other reviewers check
integration/security-sensitive changes. No subagent changes live VPS state.

## Acceptance

1. One exhaustive required inventory includes engines, CLIs/SDKs, native plugins,
   server software, web/browser/voice resources and Hermes integration contracts.
2. Default VPS installation selects it; intentionally partial modes are labelled
   partial and cannot claim full readiness. Unsupported full targets fail clearly.
3. Each component has an actual install method and native artifact check. Missing
   dependencies, unavailable images or native scan rejection remain failures.
4. Independent branches finish even after another failure; receipts never contain
   credentials/native account output or invented successful service state.
5. Unit/security/contract tests and repository Doctor pass; release metadata agrees.
6. The VPS's observed release and component evidence are read back. Real credentials
   and persistent services are preserved; no account/live acceptance is inferred.
7. Push only `main`; list exact incomplete gates if external prerequisites or the
   mandatory native security decision prevent the user's all-connected outcome.

## Native execution evidence — 2026-09-05

The targeted repair ran against root-owned reviewed candidate code, not a
writable operator service manifest. The full dependency batch completed all
14 independent steps; **13 passed and Ponytail failed**. Its retained receipt is
`/var/lib/station/dependency-install/20260905T142502276303Z.json` on the Host.
Earlier failed attempts are retained, not rewritten as successful installations.

Observed installation/readback:

- Langfuse, Honcho, Hindsight and ChatbotX: all **20 image entries / 19 unique
  image references** pulled and verified by digest, platform and actual local
  image ID. Each has a private manifest-bound service-software receipt.
- Actual Hermes environment: native MCP, memory and Langfuse imports passed;
  voice/messaging dependencies and isolated audio checks passed. Operator memory
  SDKs are separate from the Hermes-compatible versions.
- Crawl4AI and ScrapeGraphAI: fresh-home native health/browser probes passed.
  Strix CLI, TigerVNC packages and the existing local Parakeet service passed
  their respective software checks; no Strix scan or VNC display was started.
- The complete CLI toolchain, including ChatbotX, passed version checks and was
  published as immutable shared software without sharing operator credentials.
- The pinned Ponytail tree reproduced the normal native **DANGEROUS / BLOCKED**
  scan with 90 findings. It was not installed, filtered or enabled. Review then
  found that upstream permits a persisted scanner opt-out; Station must refuse
  this known-blocked pin before activation even when native scanning is disabled.
- Seventeen pre-recorded protected configuration/credential fingerprints remained
  unchanged after the software batch. No credential contents were copied into
  the audit or displayed.

Native execution exposed and corrected two real Ubuntu compatibility defects:
the distro's root-owned `/usr/bin/env` alias to Rust coreutils was rejected as a
non-regular executable, and inherited SSH working directories caused `uv` to
probe an inaccessible `/home/moonbase/uv.toml`. Native executable trust now
validates the resolved root-owned target (including legitimate coreutils hard
links); Station manifests/receipts retain strict single-link checks. Operator
commands explicitly use the operator's working directory.

The pre-publication inventory verified 15 of 18 requirements. Its three failures
were the known Ponytail block, AGK's unchanged official 11.25 controls versus
the newer reviewed source, and the expected guided-setup binding mismatch when
auditing candidate code instead of the active immutable release. All eight AGK
refresh targets matched official prior-release bytes; only launcher, controller
and provider software need refresh. No customized controls were silently adopted.

Final source review also required a mandatory native full-stack checkpoint
before full bootstrap can record success. An installer exit code alone is not
proof that the final artifacts, imports and loaded services still match.

The four server applications remain **software installed, configuration
required**. No application containers, public listeners, migrations, demo users,
secrets or profile/account bindings were created by this repair. These facts do
not establish an operational or fully connected system. Immutable publication,
CI and post-publication native readback are separate remaining acceptance gates.
