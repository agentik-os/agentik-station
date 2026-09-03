# Build Doctrine

## PLAN FIRST
Clarify mission, users, success, non-goals, constraints, graph and acceptance before implementation.

## GRAPH LOOP
For each workflow iterate:
1. actors;
2. states;
3. transitions;
4. capabilities;
5. dependencies;
6. permissions;
7. failure modes;
8. recovery paths;
9. evidence points;
10. evals.

When implementation changes the graph, update the graph and re-run validation.

## VERIFICATION ENGINEERING
A requirement without a verification method is incomplete. Prefer machine-verifiable evidence for deterministic claims and explicit reviewer evidence for judgment calls.

## LIVE TEST
Configuration is not proof. Exercise actual routes in the target environment.

## FRESH SESSION
Critical workflows and persistent automations must work without relying on hidden conversational state or an already-warmed agent session.
