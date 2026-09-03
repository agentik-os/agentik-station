# Ponytail Reference

Repository:
- https://github.com/DietrichGebert/ponytail

Hermes installation:

```bash
hermes plugins install DietrichGebert/ponytail --enable
```

Restart Hermes after installation.

Agentik policy:
- canonical for DevOps/Builder/Engineering OS
- pinned revision in `agentik.lock`
- review lifecycle hooks/commands restricted to trusted operators where relevant
- never treat minimal code as permission to remove security/validation/accessibility requirements
