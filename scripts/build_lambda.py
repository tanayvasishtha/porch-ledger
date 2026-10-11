# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Build the Lambda deployment package.

`uv export` pins the runtime deps, `uv pip install --target` resolves
Linux wheels (arm64 first, x86_64 fallback when a wheel is missing), then
the porch package, the demo house fixture and run.sh land on top. The
result is zipped with explicit permissions so run.sh stays executable
when packaged from Windows.
"""

import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BUILD = ROOT / ".build"
TARGET = BUILD / "lambda"
ZIP = BUILD / "lambda.zip"
MAX_UNZIPPED = 240 * 1024 * 1024  # Lambda limit is 250 MB

PRUNE_DIRS = {"__pycache__", "tests", "test"}
PRUNE_SUFFIXES = {".pyc", ".pyi"}


def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)  # type: ignore[arg-type]


def export_requirements() -> Path:
    req = BUILD / "requirements.txt"
    out = run(
        ["uv", "export", "--no-dev", "--frozen", "--no-hashes", "--no-emit-project"],
        cwd=BACKEND,
    )
    req.write_text(out.stdout, encoding="utf-8")
    return req


def install_deps(req: Path) -> str:
    # Lambda python3.12 runs on AL2023 (glibc 2.34); manylinux_2_28 fits.
    for platform in ("aarch64-manylinux_2_28", "x86_64-manylinux_2_28"):
        try:
            run(
                [
                    "uv", "pip", "install",
                    "--target", str(TARGET),
                    "--python-platform", platform,
                    "--python-version", "3.12",
                    "--only-binary", ":all:",
                    "-r", str(req),
                ]
            )
            return "arm64" if platform.startswith("aarch64") else "x86_64"
        except subprocess.CalledProcessError as exc:
            # Resolution failure means a missing wheel for this platform.
            if "no solution" in (exc.stderr or "").lower():
                print(f"no {platform} wheel for a dependency; trying the next")
                shutil.rmtree(TARGET, ignore_errors=True)
                TARGET.mkdir(parents=True)
                continue
            print(exc.stderr)
            raise
    raise SystemExit("no Lambda platform had wheels for all dependencies")


def copy_app() -> None:
    shutil.copytree(BACKEND / "src" / "porch", TARGET / "porch", dirs_exist_ok=True)
    (TARGET / "fixtures").mkdir(exist_ok=True)
    shutil.copy(ROOT / "fixtures" / "house.demo.json", TARGET / "fixtures")
    shutil.copy(ROOT / "infra" / "run.sh", TARGET / "run.sh")


def prune() -> None:
    for path in sorted(TARGET.rglob("*")):
        if path.is_dir() and path.name in PRUNE_DIRS:
            shutil.rmtree(path)
        elif path.is_file() and path.suffix in PRUNE_SUFFIXES:
            path.unlink()


def measure() -> int:
    total = sum(p.stat().st_size for p in TARGET.rglob("*") if p.is_file())
    print(f"package contents: {total / 1024 / 1024:.1f} MB unzipped")
    if total > MAX_UNZIPPED:
        raise SystemExit(f"package exceeds 240 MB ({total / 1024 / 1024:.1f} MB)")
    return total


def write_zip() -> None:
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(TARGET.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(TARGET).as_posix()
            info = zipfile.ZipInfo(rel)
            mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
            if path.name != "run.sh":
                mode &= ~stat.S_IXUSR & ~stat.S_IXGRP
            info.external_attr = mode << 16
            zf.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED)
    print(f"zip: {ZIP.stat().st_size / 1024 / 1024:.1f} MB -> {ZIP}")


def main() -> None:
    with tempfile.TemporaryDirectory():
        shutil.rmtree(TARGET, ignore_errors=True)
        TARGET.mkdir(parents=True)
        ZIP.unlink(missing_ok=True)
        req = export_requirements()
        arch = install_deps(req)
        copy_app()
        prune()
        measure()
        write_zip()
        print(f"built for {arch}")


if __name__ == "__main__":
    sys.exit(main())
