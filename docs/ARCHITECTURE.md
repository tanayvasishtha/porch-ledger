# Architecture

## Dependencies and why

- pydantic: typed models at every external boundary (settings, API payloads, tool IO).
- pydantic-settings: one Settings object fed by PORCH_ env vars, frozen and validated.
- rapidfuzz: fuzzy name matching for delivery label OCR in the pure domain (token_set_ratio).
- tzdata: IANA timezone database so zoneinfo works on hosts without a system tz database (Windows dev machines).
- fastapi: REST and media endpoints in porch.api (routing, validation, OpenAPI).
- uvicorn: ASGI server for `porch serve`.
- mcp: Model Context Protocol Python SDK v2 for the household tools over Streamable HTTP.
- httpx (dev): Starlette TestClient transport for API tests.
- hatchling: PEP 517 build backend for the src-layout `porch` package.
- pytest: unit and integration tests.
- hypothesis: property tests for the pure engine and geometry code.
- mypy: static types, strict mode, pydantic plugin.
- ruff: lint and format in one tool.
