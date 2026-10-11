set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

check-prose:
    uv run scripts/check_prose.py

check: check-prose
