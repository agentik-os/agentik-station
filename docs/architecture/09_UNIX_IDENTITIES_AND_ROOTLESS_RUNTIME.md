# Unix identities and rootless runtime

Each Zone receives a distinct Unix user **and its own primary group**. Zone directories are not group-shared through a global Station group.

Examples:

```text
z-private
z-agentik
z-factory
z-lab
z-c-moonbase-dev
z-p-verba-dev
```

Zone users receive private homes under `/var/lib/station/users/` and subordinate UID/GID ranges for rootless Podman. Human/operator cross-Zone access is explicit via sudo/approved ACLs, not implicit group membership.
