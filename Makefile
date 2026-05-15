.PHONY: format lint test quality

format:
	python -m ruff format .
	python -m ruff check --fix .

lint:
	python -m ruff format --check .
	python -m ruff check .
	python -m compileall cartograph
	python -m mypy

test:
	python -m pytest -q

quality: lint test
