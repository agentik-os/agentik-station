# ChatbotX default installation — Station 11.27

Scope: the [planned integration](2026-09-05-chatbotx-install-plan.md) adds client
software to the Linux Host and personal macOS/Linux Workstation installers.
Hermes remains the orchestrator. This is not ChatbotX application hosting,
account acceptance, campaign execution, or a second Station messaging gateway.

## Reviewed upstream and implementation

- ChatbotX source: `77bd6b17b23dcfb15a0a7031374bde31ceec9b86`.
- Published CLI: `chatbotx@0.1.3`, exact registry integrity and CJS SHA-256 in
  `config/versions.lock` and `resources/chatbotx/RESOURCE.json`.
- Native no-shebang entry runs through an explicit managed Node launcher, with
  lifecycle hooks disabled. New CLI state uses `umask 077`; existing personal
  state is neither adopted nor repaired implicitly.
- Version/help acceptance uses a fresh private HOME and cleared credentials.
  Upstream's configured version branch fetches a schema and reports `0.1.0`;
  it must not be used to probe an enrolled workspace.
- Hermes client SDK comes from its reviewed MCP extra; Workstation installs
  it through the frozen upstream lock. Both installers reject missing native
  SDK support. Native imports do not consult the Host operator's credentials.
- The optional remote MCP template is disabled, explicitly non-lazy, and denies
  raw tools, resource/prompt utilities, sampling and elicitation. No local npm
  MCP server is installed: that upstream package is not published.
- Full self-hosting requires a separate reviewed deployment. The upstream
  compose's mutable images, example credentials, public ports, migrations and
  broad Docker pruning are not accepted installer defaults.

The [resource guide](../../resources/chatbotx/README.md) contains the exact
paths, scoped credential procedure, API/schema-origin risks, native HOME versus
Hermes-profile distinction and MIT/commercial license boundaries.

## Findings corrected before publication

1. A metadata-only executable check could accept altered installed CJS bytes.
   Both installers now bind executable bytes to the reviewed digest before
   execution; Workstation also compares every copied resource to its source.
2. Operator-owned code could change between the Host source check and inventory.
   The inventoried CJS digest is now pinned before staging or public-link changes;
   copy/final-inventory checks protect the subsequent publication. Regressions
   cover first publication and an already-published retry.
3. Hermes resource/prompt utilities bypass the raw-tool include filter, and its
   lazy cached-utility path does not reapply those flags. The template now
   disables utilities and lazy registration explicitly. The disabled connection
   was never automatically enabled during this audit.
4. Native Workstation inspection revealed the MCP client SDK was absent even
   though a configuration template could be parsed. The installer now installs
   the locked extra and checks real SDK availability, not a simulated gate.

Independent final source review confirmed the inventory race repair and the
template restrictions. No reviewer modified personal profiles or production.

## Validation record

The first packed macOS candidate installed successfully in
`/private/tmp/stnf.jGxixp/station`: 21 required software checks passed, native TUI
and synthetic session acceptance passed, and all 14 protected personal-file
fingerprints remained unchanged. That candidate predates the MCP SDK addition
and final utility-filter template; it is retained as intermediate evidence, not
acceptance of those later changes.

A full Python run under `/private/tmp` encountered 52 failures and 98 setup
errors: macOS inherited group `wheel` there, while identity fixtures require the
operator's `staff` group. The temporary root's observed group was 0 and the
operator's group was 20. Validation was rerun in a fresh user-owned temporary
namespace with group 20; no runtime permission guard was relaxed to pass it.

Final source validation:

- **1,572 Station/Factory tests passed**, with 21 Linux-only skips on macOS.
- **168 npm tests passed**, including eight focused ChatbotX installation,
  package-drift, launcher, credential-preservation and required-failure cases.
- **170 final focused contract/bootstrap/dependency tests passed** after the
  MCP SDK and isolated Host import checks were added.
- The packed npm consumer installed offline, exposed its executable, shipped
  all four ChatbotX resource files and produced a read-only plan without hooks.
- Repository Doctor, shell syntax and diff hygiene passed. Deterministic
  release metadata is regenerated and checked for the published tree.

Final fresh macOS consumer acceptance passed in
`/private/tmp/stnf.ou3f1e/station`, with receipt
`/private/tmp/stnf.ou3f1e/native-acceptance.json`:

- Package `@agentik-os/station@11.27.0`, 689 files; integrity
  `sha512-zwS8SwyLCwikLJj3fme7NJEuMvGe2aMKzEMOdDvlG1eaHuKabIGUo4ROnIs4ttDxXoyWRkzQCe5AxJU1XpAeLg==`.
- Installation exit 0, `ready-for-setup`, **21 required checks verified**.
- Real MCP SDK imports, native template/header interpolation, disabled-server
  behavior and zero synthetic raw/utility registration passed. The native test
  observed **zero network attempts and zero child-process attempts**; this is
  not live remote MCP discovery or account acceptance.
- Native AGK navigation exercised **10 views at three terminal sizes** and
  exited 0. Synthetic `/bin/cat` session create/input/readback/rename/respawn/
  restart/archive/purge checks passed without model calls.
- All **14 protected personal-file fingerprints remained unchanged**, including
  ChatbotX configuration/cache. No gateway service was created or activated.

The committed CI workflow also installs the packed consumer on native Linux and
runs package tests on Linux/macOS. Its outcome belongs to the exact published
commit's [Actions run](https://github.com/agentik-os/agentik-station/actions), not
this local macOS receipt. Source push and CI do not publish to the npm registry.

## Explicitly unaccepted external gates

- No production VPS upgrade or live Host installation was performed in this
  release audit. Host source/security tests and native Linux Workstation CI do
  not substitute for production Host acceptance.
- No real ChatbotX workspace token, live MCP discovery/tool call, campaign,
  message, self-hosted database or Docker service was used or created.
- Discord gateway activation and paid model/audio calls were not performed.
- A token pasted in chat was treated as exposed, never copied into tools/files
  or used. Existing npm authentication returned HTTP 401. GitHub source push
  does not mean npm publication; fresh official authentication is required.
- Native acceptance fixtures and private receipts are retained for deliberate
  cleanup. Only probe-created disposable subdirectories and synthetic sessions
  are removed by the tests themselves.
