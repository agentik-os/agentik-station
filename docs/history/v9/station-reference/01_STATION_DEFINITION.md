# Station Definition

**Station** is the complete AGK/Agentik operating environment installed around Hermes.

It includes four planes:

```text
HOST PLANE
Linux · SSH/Tailscale · firewall · users · volumes · systemd · backup

CONTROL PLANE
AGK desired state · registries · policies · lockfiles · fleet metadata · evidence

EXECUTION PLANE
Hermes installs/homes · profiles · sessions · Kanban · delegation · tools · sandboxes

INTERACTION PLANE
Dedicated OS Discord bots/channels · Agentik UI/API · approvals · notifications
```

A Station can host one organization or, for Operator-owned workloads only, several explicit trust zones. A production client receives its own Station/Node/VPS.

## Station invariants

- Hermes is the execution kernel, never forked casually to implement AGK behavior.
- AGK policy is declarative; enforcement compiles to Hermes managed config, plugins/hooks, Linux boundaries and tool permissions.
- Stable workloads are pinned; upstream Hermes is continuously checked in LAB.
- OSs are built/upgraded through Builder + Librarian.
- Secrets are references, never package contents.
- A canonical OS has a dedicated Nano Director bot/channel.
- Every durable action leaves evidence.
- Recoverability is a feature, not an operations afterthought.
