# Web Product stack

Station's preferred product baseline is Next.js + React for the app, Convex for reactive backend/state, Clerk for identity, Stripe for billing, Vercel for deployment, Tailwind CSS for styling, shadcn/ui for Project-owned components and Lucide for icons.

The catalog pins packages but does not create external accounts or store secrets. Hermes must plan the repository change, install dependencies inside the correct Project, request only the necessary provider setup, verify local tests and deployment readback, and retain rollback evidence. A Project may choose another stack by declaring the same operational contract.
