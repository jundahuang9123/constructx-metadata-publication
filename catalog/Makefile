.PHONY: test up-solid up-edc

test:
	python -m pytest

up-solid:
	CATALOG_MODE=solid docker compose --profile solid up --build

up-edc:
	CATALOG_MODE=edc docker compose --profile edc up --build

