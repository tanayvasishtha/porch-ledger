# /// script
# requires-python = ">=3.11"
# ///
"""Prose gate for tracked text files in this repo.

Fails on: em or en dashes anywhere in a scanned file, banned words in
Markdown files, and TODO or FIXME markers in any scanned file except
this script itself. Prints one `path:line: reason` line per violation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SELF_PATH = Path(__file__).resolve()
SCAN_SUFFIXES = {
    ".md",
    ".py",
    ".kt",
    ".kts",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".html",
    ".css",
}
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
BANNED_WORDS = (
    "seamless",
    "robust",
    "leverage",
    "delve",
    "harness",
    "empower",
    "elevate",
    "unlock",
    "journey",
    "landscape",
    "game-changer",
    "cutting-edge",
    "revolutionary",
    "comprehensive",
    "holistic",
)
BANNED_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(word) for word in BANNED_WORDS) + r")\b",
    re.IGNORECASE,
)
MARKER_RE = re.compile(r"TODO|FIXME")


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()]


def scan_file(path: Path, rel_posix: str) -> list[str]:
    is_self = path.resolve() == SELF_PATH
    is_markdown = path.suffix == ".md"
    violations: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if EM_DASH in line:
            violations.append(f"{rel_posix}:{lineno}: em dash (U+2014)")
        if EN_DASH in line:
            violations.append(f"{rel_posix}:{lineno}: en dash (U+2013)")
        if is_markdown:
            for match in BANNED_RE.finditer(line):
                violations.append(
                    f"{rel_posix}:{lineno}: banned word '{match.group(0)}'"
                )
        if not is_self and MARKER_RE.search(line):
            violations.append(f"{rel_posix}:{lineno}: TODO/FIXME marker")
    return violations


def main() -> int:
    all_violations: list[str] = []
    scanned = 0
    for path in tracked_files():
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        rel_posix = path.relative_to(REPO_ROOT).as_posix()
        scanned += 1
        all_violations.extend(scan_file(path, rel_posix))
    if all_violations:
        for violation in all_violations:
            print(violation)
        print(f"check_prose: {len(all_violations)} violation(s)")
        return 1
    print(f"check_prose: OK ({scanned} files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
