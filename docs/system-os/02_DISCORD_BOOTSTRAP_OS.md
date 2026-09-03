# Discord Bootstrap OS

Dedicated system OS for provisioning/reconciling a Discord organization cockpit.

## Privilege model

`Administrator` is bootstrap-window only. After successful readback, Station requires runtime least privilege; Doctor fails while bootstrap Admin remains unnecessarily enabled.

## Responsibilities

- inventory current guild;
- compile desired state from organization + installed OS manifests;
- plan/diff before apply;
- adopt/extend by default, not destructive recreate;
- roles/categories/channels/overwrites;
- dedicated OS bot/channel binding after bot credential enrollment;
- slash command/help/readback;
- immutable Discord ID binding registry;
- drift reconciliation.

Creating a Discord application/token is treated as an external credential/application enrollment step unless an officially supported API/control-plane capability exists and is explicitly approved.
