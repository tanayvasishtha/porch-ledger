# Architecture

## Dependencies and why

- pydantic: typed models at every external boundary (settings, API payloads, tool IO).
- pydantic-settings: one Settings object fed by PORCH_ env vars, frozen and validated.
- hatchling: PEP 517 build backend for the src-layout `porch` package.
- pytest: unit and integration tests.
- hypothesis: property tests for the pure engine and geometry code.
- mypy: static types, strict mode, pydantic plugin.
- ruff: lint and format in one tool.
