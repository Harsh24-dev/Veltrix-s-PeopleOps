.PHONY: install run test ingest

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	pytest -q
