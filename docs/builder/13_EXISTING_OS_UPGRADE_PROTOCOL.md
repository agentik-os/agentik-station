# Upgrade Existing OSs to Full Contract

Builder is responsible for existing OS debt, not only new builds.

## Audit matrix

For every installed/registry OS, Builder produces a contract matrix:

```text
package                  PASS/GAP
Nano Director            PASS/GAP
NanoTeam                  PASS/GAP
profiles                  PASS/GAP
ordered skills            PASS/GAP
deterministic programs    PASS/GAP
MCP/tool contracts        PASS/GAP
knowledge/memory scopes   PASS/GAP
provider routes           PASS/GAP
workflows                 PASS/GAP
automations               PASS/GAP
evaluations               PASS/GAP
Discord control surface   PASS/GAP
doctor                    PASS/GAP
rollback                  PASS/GAP
recovery artifact         PASS/GAP
Librarian 15 inputs       PASS/GAP
Dedicated bot commands    PASS/GAP
fresh-session acceptance  PASS/GAP
```

## Upgrade flow

`audit -> Librarian handoff -> candidate package -> tests -> Gauntlet -> migration rehearsal -> dedicated bot bind/readback -> fresh-session acceptance -> release`.

No in-place production mutation before an immutable candidate exists and rollback is proven.
