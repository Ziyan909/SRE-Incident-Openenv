.PHONY: run test validate smoke benchmark-regression check baseline benchmark

PYTHON := .venv/bin/python

run:
	$(PYTHON) -m uvicorn api.server:app --host 0.0.0.0 --port 8000

test:
	$(PYTHON) -m unittest discover -s tests -v

validate:
	openenv validate

smoke:
	$(PYTHON) scripts/submission_check.py

benchmark-regression:
	$(PYTHON) scripts/benchmark_regression_check.py

check: test validate smoke benchmark-regression

baseline:
	$(PYTHON) baseline.py

benchmark:
	$(PYTHON) -c "from env.baseline_runner import run_benchmark; print(run_benchmark().model_dump(mode='json'))"
