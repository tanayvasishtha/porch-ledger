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
- pillow: image crop for delivery label OCR in enrich, and synthetic tape frames in tests/demo.
- hatchling: PEP 517 build backend for the src-layout `porch` package.
- pytest: unit and integration tests.
- hypothesis: property tests for the pure engine and geometry code.
- mypy: static types, strict mode, pydantic plugin.
- ruff: lint and format in one tool.

## TV app dependencies (Gradle, tv/)

- Android Gradle Plugin 8.13.2 + Kotlin 2.4.21: the app toolchain; AGP 8.x line keeps the known Kotlin plugin wiring.
- Compose BOM 2026.04.01 + androidx.tv:tv-material 1.1.0: TV UI toolkit; the 2026.09 BOM requires AGP 9 and compileSdk 37, so the newest BOM that still builds on AGP 8 is pinned.
- Fraunces + Source Sans 3 TTFs: bundled typefaces under res/font, OFL texts in assets/licenses; Source Sans keeps unslashed zeros for time spans.
- Ktor client (OkHttp engine) + kotlinx.serialization: TV API client over the shared OpenAPI/golden contract; okhttp pinned to 5.4 because 5.5 requires compileSdk 37.
- DataStore preferences: persists the last good visit list for offline start.
- Coil 3.5.0: hero image loading on TV; 3.6.x requires compileSdk 37, 3.5 stays on 36.
- Roborazzi + Robolectric + coil-test: JVM screenshot and focus tests, goldens in tv/app/src/test/screenshots.
- Turbine + kotlinx-coroutines-test: StateFlow assertions in ViewModel tests.
- Spotless (ktlint) + detekt: TV code style and complexity gates; detekt runs on main sources only.
