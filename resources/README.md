# Station resource catalog

This is the canonical, versioned catalog of reusable development resources and reviewed stack recipes. In an installed release it lives at `/opt/station/current/resources`; `/srv/station/3_SHARED/resources` is a human-readable pointer, and each Project records its chosen resources in its own `resources/` directory.

Resources are not globally injected into every repository. Hermes or a coding executor resolves the owning Zone and Project, prints the exact plan with `station resource stack-plan`, then installs only the Project contract's choices. Authentication and provider projects remain explicit setup gates.

The default `web-product` recipe uses Next.js, React, Convex, Clerk, Stripe, Tailwind CSS, shadcn/ui and Lucide. It is a strong default, not a lock-in: other stacks are allowed when the Project contract documents dependency pins, secrets, deployment, verification and rollback.

`discord-js-sdk` is a separate, pinned SDK resource for typed Discord API
extensions. It does not run a bot or a Gateway connection: Hermes remains the
single messaging gateway and every consumer must be explicitly Zone-scoped.
