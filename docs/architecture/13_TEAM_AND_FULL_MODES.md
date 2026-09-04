# Full and Team installation modes

Station uses one architecture and two bootstrap modes. This avoids maintaining a second product for companies.

## Full mode

Designed for an operator building Agentik itself, private systems, OSs and multiple Organizations/Projects. It maps to Host role `core` and installs System, Private, Agentik, Factory and Lab base Zones.

## Team mode

Designed for one company or team. It maps to Host role `team` and installs only System Zones plus the explicitly seeded `ORGANIZATIONS/<organization>/<environment>` Zone and its Projects. There is no Station-wide Private Zone.

Personal context in Team mode is represented by **member scopes inside the Organization Zone**. Each member receives a stable principal, Discord binding, Composio identity, memory namespace and credential namespace. Shared Organization OSs may act for the team while member-scoped capabilities resolve the correct human account.

A member scope is not a hard Unix isolation boundary. Data requiring strong filesystem isolation must use a separate Zone.

## Placement

The same Organization or Project contract works locally or on a remote Host. Placement never changes its internal structure.
