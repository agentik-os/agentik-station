# Ponytail native security-scan review — 2026-09-05

## Outcome and scope

Ponytail remains **NOT_INSTALLED** on the reviewed VPS. The native Hermes installer blocked its installation; the engineering plugin and its commands are not accepted as available. This is an installation/security-review blocker, not evidence that a previously operational Ponytail runtime degraded.

The deployment verifier supplied the native scan readback from the full VPS bootstrap's AI-stack stage. This independent review inspected Station's installation command, pinned upstream sources and release assets. It did not execute Ponytail, change the VPS, or independently reproduce all scanner findings.

| Field | Observed or reviewed value |
| --- | --- |
| Repository | `DietrichGebert/ponytail` |
| Release | `v4.9.0` |
| Exact commit | `0a4dd63ad4541f4f655c4108a295916f3c1d8fda` |
| Native source classification | `community` |
| Native verdict / decision | `dangerous` / `BLOCKED` |
| Native finding count | `90` |
| Installation outcome | `NOT_INSTALLED`; no security bypass accepted |

The attempted native command was:

```bash
hermes plugins install DietrichGebert/ponytail \
  --ref 0a4dd63ad4541f4f655c4108a295916f3c1d8fda --enable
```

This is not simply a wrong repository or missing plugin entrypoint: the pinned tree contains a [native Hermes manifest](https://github.com/DietrichGebert/ponytail/blob/0a4dd63ad4541f4f655c4108a295916f3c1d8fda/plugin.yaml), and its [README explicitly documents Hermes plugin installation](https://github.com/DietrichGebert/ponytail/tree/0a4dd63ad4541f4f655c4108a295916f3c1d8fda#hermes-agent). The repository also contains other host adapters, benchmarks and development assets.

## Critical findings: evidence, not blanket clearance

The deployment verifier identified two critical traversal findings:

- `benchmarks/agentic/README.md:52`: the safety-task table mentions `../../etc/passwd` as input that must **not** escape a base directory. The [pinned benchmark description](https://github.com/DietrichGebert/ponytail/blob/0a4dd63ad4541f4f655c4108a295916f3c1d8fda/benchmarks/agentic/README.md) was independently read and confirms this negative-test purpose.
- `benchmarks/agentic/tasks.py:68`: the supplied native report excerpt points to a comment describing the same safe-path traversal test. Its exact location and excerpt come from the deployment verifier; this reviewer did not independently retrieve that file.

These contexts support a **benchmark false-positive diagnosis for those two matches**, rather than a finding that the Hermes runtime traverses into `/etc/passwd`. The remaining findings were reported mainly in benchmark/test tooling, examples, workflows and instruction text. They were not individually cleared by this review. A plausible false positive does not convert the native `dangerous` verdict into an installation approval or prove the entire repository safe.

## Runtime review and compatibility caveats

The complete pinned [Hermes entrypoint](https://github.com/DietrichGebert/ponytail/blob/0a4dd63ad4541f4f655c4108a295916f3c1d8fda/__init__.py) uses standard-library imports, reads local configuration and bundled skill text, injects context, and registers six skills/commands plus pre-LLM and pre-gateway hooks. No network, subprocess, credential-store-reading or file-writing implementation was found in this entrypoint. This narrow observation is not a full-tree security audit.

Important boundaries remain:

- `_current_mode` is process-global, not keyed by session, profile or OS instance.
- Default configuration uses `XDG_CONFIG_HOME` or the Unix `HOME` configuration directory, not `HERMES_HOME`. Separate Hermes profiles alone do not establish separate Ponytail defaults.
- The gateway rewrite helper returns "not denied" when gateway/event/access-checker/source context is missing, although checker exceptions deny access. It must not be treated as an independent fail-closed authorization boundary.
- Enablement must be scoped to the intended engineering principals, with native gateway slash-command access controls verified. Upstream's [post-install instructions](https://raw.githubusercontent.com/DietrichGebert/ponytail/0a4dd63ad4541f4f655c4108a295916f3c1d8fda/after-install.md) explicitly warn about shared gateways and process-local mode.

## Permitted next action

The reviewed [v4.9.0 release assets](https://github.com/DietrichGebert/ponytail/releases/expanded_assets/v4.9.0) expose only complete source ZIP and tar archives, not a separate reviewed Hermes distribution.

Keep the failed-install evidence and native guard intact. Seek an upstream-reviewed scanner correction for the demonstrated false-positive contexts, or an upstream-published reviewed plugin distribution. Any candidate requires a reviewed immutable pin, a fresh run through the normal native security guard, and then scoped runtime/command/ACL acceptance. A future warning requiring confirmation must receive the applicable explicit review; it is not automatically accepted here.

Do not remove or filter flagged files merely to make this source pass, manually copy the plugin into place, introduce a trust exception, disable scanning, or use another installation route to evade the decision. Native `--force` does not override this dangerous verdict. Broad authorization to finish installation does not authorize bypassing security controls.

Station's existing reviewed engineering/reuse guidance can continue to apply while this is unresolved. It is not a substitute installed Ponytail plugin and must not be reported as one. Independent components may be verified separately, but Ponytail-dependent acceptance remains outstanding.
