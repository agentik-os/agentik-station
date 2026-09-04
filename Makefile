.PHONY: plan doctor test factory validate

plan:
	./station plan --host-id station-core-01 --role core

doctor:
	PYTHONDONTWRITEBYTECODE=1 ./station doctor --repo

test:
	PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider

factory:
	PYTHONDONTWRITEBYTECODE=1 python3 factory/tests/run_tests.py

validate: doctor test factory
