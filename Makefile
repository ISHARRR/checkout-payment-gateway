.PHONY: install
install:
	@poetry install 

.PHONY: run
run:
	@poetry run python main.py

.PHONY: test
test: 
	@poetry run python -m pytest -vv

.PHONY: check
check:
	@poetry run ruff check .
	@poetry run ruff format --check .

.PHONY: integration
integration:
	@RUN_BANK_INTEGRATION=1 poetry run python -m pytest -m integration -vv
