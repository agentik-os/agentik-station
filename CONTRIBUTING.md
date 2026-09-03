# Contributing to Agentik Station

## Required workflow

1. open with an explicit objective and acceptance criteria;
2. add or update typed contracts before broad implementation;
3. create a worktree for mutable parallel coding;
4. make the smallest justified change;
5. add a regression test for every bug/security finding;
6. run all verification commands below;
7. update maturity claims and next repair actions honestly;
8. leave no generated caches or local secrets in the release tree.

```bash
python -m pip install -e '.[dev]'
PYTHONDONTWRITEBYTECODE=1 ./station doctor --repo
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python factory/tests/run_tests.py
```

## Pull request claim language

Use exact evidence levels:

- **prepared**: design/plan only;
- **observed**: executor/process was seen running;
- **reported**: executor said it completed;
- **verified**: deterministic test/review/Doctor passed;
- **read back**: external/installed state was queried after mutation;
- **accepted**: initial acceptance criteria were proved.

A new connector, OS, or external integration cannot be called operational from mocks or file presence alone.
