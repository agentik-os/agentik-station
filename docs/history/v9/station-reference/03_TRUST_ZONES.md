# Operator Station Trust Zones

Hermes profiles provide identity/state separation, but a profile alone is not treated as a hard OS security boundary. Station therefore isolates high-value domains with separate Unix users, HERMES_HOME values and storage roots; LAB additionally uses disposable/sandboxed execution.

| Zone | Purpose | Secrets | Raw memory | Code write | Internet/tools | Cross-zone default |
|---|---|---|---|---|---|---|
| `station-system` | control, updater, evidence, fleet metadata | system refs only | operational | limited | controlled | deny |
| `private-self` | private self-development and private personal OSs | private refs | private | normally no | scoped | deny |
| `personal-projects` | Operator-owned projects | per-project refs | per-project | yes per project | scoped | deny |
| `agentik-dev` | Agentik/AGK product engineering | dev/staging refs | product | yes | dev tools | deny private/client |
| `os-factory` | Builder, Librarian, DevOps, OS packaging | factory refs | build/research | yes | research/dev | deny private/client raw |
| `lab` | Hermes edge/canary and untrusted experiments | no prod secrets | synthetic | yes disposable | broad but sandboxed | deny |

## Hard implementation boundary

Recommended Linux identities:

```text
station-admin      human sudo/admin only
station-system     Station control/update/evidence services
operator-private     private-self Hermes home
operator-projects    personal-project controller; per-project containers/volumes
agentik-dev        Agentik product Hermes home/workspaces
os-factory         Builder/Librarian/DevOps Hermes home/workspaces
station-lab        canary Hermes checkout; synthetic/no production credentials
```

For a highly sensitive personal project, promote it from `operator-projects` into its own Unix user or dedicated Node.

## Why not one giant Hermes home?

- accidental filesystem access becomes easier;
- state/boards can become semantically mixed;
- one credential pool becomes tempting;
- backups/offboarding become harder;
- agent errors become security events.

Station favors boring boundaries over prompt-only isolation.
