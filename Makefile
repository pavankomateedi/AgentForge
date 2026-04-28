.PHONY: install dev test smoke clean

install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn agent.main:app --host $${HOST:-127.0.0.1} --port $${PORT:-8000} --reload

test:
	pytest -v

eval:
	pytest

eval-live:
	pytest -m live -v

smoke:
	@curl -s http://127.0.0.1:$${PORT:-8000}/health
	@echo
	@curl -s -X POST http://127.0.0.1:$${PORT:-8000}/chat \
		-H "Content-Type: application/json" \
		-d '{"patient_id":"demo-001","message":"brief me"}' | python -m json.tool

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov dist build *.egg-info
