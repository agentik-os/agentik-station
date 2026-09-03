# GitHub Publishing

Recommended repository name: `agentik-os/agentik-station`.

Recommended initial posture: **private** until a clean-room install and security review pass on a fresh VPS.

Before first release:

1. create the empty repository;
2. push this tree as the initial commit;
3. protect `main`;
4. require `station-ci`;
5. run a fresh-host acceptance install from the Git URL;
6. record issues discovered by the install;
7. fix through PRs;
8. tag the first internal release only after rollback/recovery and Discord fresh-session acceptance pass.

Do not add tokens, OAuth material, client data or private runtime state to the repository.
