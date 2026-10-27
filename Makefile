.PHONY: test evals serve smoke

test:
	pytest -q

evals:
	python -m evals.run --all

serve:
	uvicorn app.main:app --reload --port 8000

smoke:
	python scripts/smoke_test.py
