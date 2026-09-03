# Linux Foundation

Station follows the Filesystem Hierarchy Standard instead of hiding operational assets inside one operator home directory.

```text
/etc/station       configuration / desired host policy
/opt/station       installed Station software
/srv/station       operational human-readable layout
/var/lib/station   machine state
/var/log/station   logs
/var/backups/station backup staging
/run/station       temporary state
```

`/srv/station` is the normal operator entry point. `/root` is never a project workspace.
