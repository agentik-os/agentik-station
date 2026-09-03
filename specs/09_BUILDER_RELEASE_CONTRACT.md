# Builder Release Contract

A release is atomic at the AGK level. `RELEASED` requires evidence for every gate:

1. locked contract descriptor validates
2. Librarian handoff exists
3. 15-input mapping reviewed
4. RED->GREEN acceptance evidence
5. independent review pass
6. security/capability pass
7. package/hash manifest pass
8. Doctor pass
9. rollback rehearsal pass
10. recovery rehearsal pass
11. dedicated Discord bot/channel/commands bound
12. Discord command + routing readback pass
13. fresh-session acceptance pass
14. automations enabled only after #13
15. final release critic pass

If any gate fails, release state remains non-terminal and the previous stable OS stays active.
