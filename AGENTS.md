# Porch Ledger: agent instructions

Entry for Build, Ship, Shape: Amazon Developer Hackathon. Ring (primary) + Fire TV tracks, AWS Builder and Open Source mini challenges.

## Layout

- `backend/` Python package `porch` (src layout, uv): `config.py` holds the single Settings object; `domain/` is pure models plus the VisitEngine; `ports.py` holds Protocols; `adapters/` covers ring, aws, weather, local; `pipeline/` covers ingest, perception, enrich, agent, ask; `api/` is the FastAPI app; `mcp_server.py`; `cli.py`. Tests live in `backend/tests/` (unit, property, contract, integration, golden).
- `tv/` Kotlin Compose for TV app, single activity, manual AppGraph.
- `echo/` Vite + Preact + TypeScript MCP client for the iPad.
- `infra/` SAM template and config.
- `fixtures/` tapes, own footage, cassettes, scenarios.
- `scripts/` repo scripts (build_lambda, evals, check_prose).
- `docs/` architecture, eval, friction log, feedback, submission.

## Gates

Only these exist so far; add recipes as components land.

- `just check-prose` (also runs as part of `just check`)

## Code rules (anti-slop)

- typed boundaries only
- no broad `except`
- no dead code or commented-out code
- functions small with one job
- comments explain why, not what
- no new dependency without a line in `docs/ARCHITECTURE.md` saying why
- no AI co-author trailers or "generated with" footers in commits (user rule)

## Commits

Small feature commits, plain messages. Never any AI co-author trailer or "Generated with" footer.

## Writing rules

- No em or en dashes anywhere in prose or comments.
- Banned words in Markdown: the enforced list is `BANNED_WORDS` in `scripts/check_prose.py`.
- No task markers in tracked files: the enforced pattern is `MARKER_RE` in `scripts/check_prose.py`.
- Every published number comes from a script in the repo.
- Run the humanizer skill on every judge-facing document.
