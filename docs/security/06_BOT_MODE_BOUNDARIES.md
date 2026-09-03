# Bot Mode Security Boundaries

## Profiles are not client isolation

Hermes profiles provide state/configuration separation, not a hard host security boundary. Therefore:

- different customer organizations MUST NOT rely only on profiles for isolation;
- serious customer organizations use separate Agentik Nodes/VPS/VM boundaries;
- bot-to-bot messaging across organizations is denied by default.

## Capability resolution

A Bot identity is never itself an authorization token.

Every privileged operation resolves:

```text
organization_id
+ os_id
+ profile_id
+ mission_id
+ environment
+ capability
```

## Bot-to-bot controls

Allowed communication must specify:

- source profile;
- target profile/team;
- allowed message classes;
- data classification;
- maximum delegation depth;
- evidence requirement;
- cross-node policy.

## Discord virtual identity

internal specialist routing display names, avatars, roles and aliases are routing/presentation metadata only. They do not change permissions.
