# Doctor Boundary Validation

The installed Doctor treats `/etc/station/zones.d/*.json` as privileged desired-state records, but it does not trust path strings merely because they are stored under `/etc`.

For every local Zone record, Doctor:

1. rejects unknown or missing fields;
2. reconstructs a typed `ZoneSpec`;
3. recalculates the canonical Zone ID and Unix identity;
4. recalculates the exact human, state, Hermes, log, run, and backup roots from `LayoutPaths`;
5. compares every stored path to the recalculated path;
6. compares the human `ZONE.json` projection to the root-owned canonical record;
7. validates `os/DESIRED.json` against the release OS catalog;
8. only then inspects filesystem objects, permissions, ownership, and symlinks.

If the record is inconsistent, Doctor fails closed and does not traverse its supplied paths.

Project manifests receive the same treatment: Project ID, containing Zone, organization, environment, human root, and runtime state root are recalculated before the filesystem is inspected.

Remote desired records are a distinct schema. They remain `NOT_INSTALLED`, contain no local filesystem roots, and are never treated as local runtime evidence.
