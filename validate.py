#!/usr/bin/env python3
"""Single gate of the APK extract module."""
from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    python = sys.executable
    scripts = [ROOT / "apkextract.py", ROOT / "validate.py", *ROOT.glob("tests/test_*.py")]
    for path in scripts:
        py_compile.compile(str(path), doraise=True)
    result = subprocess.run(
        [python, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        return result.returncode
    print("PASS apk-extract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
