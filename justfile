set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Machine JDK for the tv recipe; a real JAVA_HOME always wins.
export JAVA_HOME := env_var_or_default("JAVA_HOME", "C:/Users/Dell/AppData/Local/Programs/Microsoft/jdk-17.0.10.7-hotspot")

check-prose:
    uv run scripts/check_prose.py

[working-directory: 'backend']
backend:
    uv run ruff check
    uv run ruff format --check
    uv run mypy
    uv run pytest --cov=porch.domain --cov=porch.adapters --cov=porch.api --cov-report=term-missing --cov-fail-under=90

[working-directory: 'tv']
tv:
    ./gradlew.bat spotlessCheck detekt lint testDebugUnitTest verifyRoborazziDebug assembleRelease

check: check-prose backend tv

[working-directory: 'backend']
contracts:
    uv run python -m porch export-contracts --out ../contracts
    git -C .. diff --exit-code contracts

[working-directory: 'backend']
demo:
    uv run python -m porch demo --serve
