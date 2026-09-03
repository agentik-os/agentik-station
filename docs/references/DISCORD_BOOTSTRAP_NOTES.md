# Discord Bootstrap Notes

Current Discord role/permission rules that matter to the architecture:

- Administrator is the strongest permission and bypasses channel restrictions.
- Role hierarchy is top-down.
- An identity with Manage Roles can only affect roles below its highest role and cannot grant permissions it does not itself possess.
- Server applications can request permissions needed to create channels/edit roles, but production should request/retain only what is necessary.

Official references:
- https://support.discord.com/hc/en-us/articles/214836687-Discord-Roles-and-Permissions
- https://support.discord.com/hc/en-us/articles/206029707-Setting-Up-Permissions-FAQ

Agentik consequence:
- Administrator only during authorized bootstrap if needed
- automatic post-bootstrap demotion
- role hierarchy preflight
- idempotent non-destructive reconciliation
