set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

check-prose:
    uv run scripts/check_prose.py

[working-directory: 'backend']
backend:
    uv run ruff check
    uv run ruff format --check
    uv run mypy
    uv run pytest --cov=porch.domain --cov=porch.adapters --cov-report=term-missing --cov-fail-under=90

check: check-prose backend
