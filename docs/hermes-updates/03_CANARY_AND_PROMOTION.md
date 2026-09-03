# Canary and Promotion

## LAB application

1. assert ring=`lab` and no production credential namespaces;
2. full Station/LAB snapshot;
3. `hermes update --backup --branch main --yes`;
4. collect updater receipt and actual running version matrix;
5. `hermes config check`;
6. review/compile configuration migration rather than accepting unknown defaults blindly;
7. `hermes doctor` + `hermes hooks doctor`;
8. run Station core tests;
9. Builder/Librarian pack tests;
10. DevOps/Ponytail smoke;
11. Bot/Discord readback in test surface;
12. fresh-session acceptance;
13. parallel/Kanban/worktree regression;
14. backup/rollback rehearsal;
15. create immutable Station candidate lockfile and evidence receipt.

## Promotion

A candidate release pins the exact Hermes commit/version and all plugin commits. Stable Nodes consume that Station release rather than following `main` independently.
