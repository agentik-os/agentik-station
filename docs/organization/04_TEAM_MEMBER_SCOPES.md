# Team member scopes

A Team Station has no single Station-wide personal context. Each human is represented inside the Organization by a member principal.

A member principal owns references to:
- Discord user identity and permissions;
- Composio user / connected accounts;
- member-scoped memory namespace;
- member-scoped credential namespace;
- approval identity and evidence trail.

Shared Organization OSs remain shared. When an OS acts for a particular human, Station resolves the member principal before capability execution.

Member scopes are logical identity boundaries, not Unix filesystem sandboxes. Use a separate Zone when hard filesystem isolation is required.
