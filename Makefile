.PHONY: install lint typecheck test check serve

install:
	pip install -e ".[dev]"

lint:
	ruff check pyagenthound tests examples

typecheck:
	mypy pyagenthound

test:
	pytest -q

check: lint typecheck test

serve:
	pyagenthound serve
