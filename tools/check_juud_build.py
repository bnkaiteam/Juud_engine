#!/usr/bin/env python3
"""Check a Juud source-build record before advertising the opt-in engine path."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import setup  # noqa: E402 - import the checkout's own source fingerprint function


def verify_source_build(executable: Path) -> str:
    """Return the source fingerprint or raise ValueError for an unverified build record."""
    build = executable.parent / "BUILD.json"
    if not build.is_file() or not executable.is_file():
        raise ValueError("Juud engine binary or build record is missing. "
                         "Run setup with --setup --build --no-start first.")
    try:
        metadata = json.loads(build.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read engine build record: {error}") from error
    if metadata.get("source") != "local":
        raise ValueError("The installed engine is recorded as a Strata prebuilt, not a Juud source build. "
                         "Run setup with --setup --build --no-start.")
    expected = setup.source_hash(setup.ENGINE_SOURCES)
    if metadata.get("src") != expected:
        raise ValueError("The installed engine is recorded as built from older source. "
                         "Rebuild with --setup --build --no-start.")
    return expected


def main() -> int:
    executable = ROOT / "engine" / ("strata.exe" if sys.platform == "win32" else "strata")
    try:
        expected = verify_source_build(executable)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Juud local build record matches source fingerprint ({expected}); opt-in flags may be enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
