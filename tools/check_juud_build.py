#!/usr/bin/env python3
"""Check a Juud source-build record before advertising the opt-in engine path."""

from __future__ import annotations

import json
import os
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


def verify_windows_cuda_dll(executable: Path, environ: dict | None = None) -> None:
    """Check that Windows can find the local engine's cuBLAS DLL before it starts."""
    env = os.environ if environ is None else environ
    metadata = json.loads((executable.parent / "BUILD.json").read_text(encoding="utf-8"))
    if metadata.get("backend") not in (None, "cuda"):
        return
    toolkit = 12 if metadata.get("toolkit") == 12 else 13
    dll = f"cublas64_{toolkit}.dll"
    # Setup normally copies the build's CUDA folders into each model config. A user may instead give a
    # model its own lib_dirs, and this guard runs before setup asks which model to start. Check all configs
    # for this engine so that a valid custom directory is not rejected before that choice is known.
    model_dirs = []
    has_model_config = False
    for config in executable.parent.parent.glob("strata-*.json"):
        try:
            saved = json.loads(config.read_text(encoding="utf-8-sig"))
            if Path(saved.get("exe", "")).resolve() != executable.resolve():
                continue
            has_model_config = True
            model_dirs.extend(Path(d) for d in saved.get("lib_dirs") or [] if isinstance(d, str))
            for key, value in (saved.get("env") or {}).items():
                if key.upper() == "PATH":
                    model_dirs.extend(Path(d) for d in str(value).split(";") if d)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    # When a model config exists, the server uses its lib_dirs rather than BUILD.json's cuda_dirs.
    # A child engine also inherits PATH. Include the other standard Windows DLL search locations.
    root = env.get("SystemRoot") or env.get("windir")
    dirs = [executable.parent, *(model_dirs if has_model_config else
                                  [Path(d) for d in metadata.get("cuda_dirs") or []])]
    if root:
        dirs.extend((Path(root) / "System32", Path(root) / "System", Path(root)))
    dirs.append(Path.cwd())
    dirs.extend(Path(d) for d in (env.get("PATH") or env.get("Path") or "").split(";") if d)
    if any((directory / dll).is_file() for directory in dirs):
        return

    toolkit_name = "CUDA Toolkit 13.0" if toolkit == 13 else "a CUDA 12.x Toolkit"
    raise ValueError(
        f"Windows cannot find {dll} for the locally built CUDA {toolkit} engine. "
        "Checked the engine folder, configured or recorded CUDA folders, "
        "and the Windows DLL search path. "
        f"Install or repair {toolkit_name} with cuBLAS, then make sure the folder containing {dll} "
        "is in this model's strata-*.json lib_dirs (or PATH). Retry RUN-JUUD.bat."
    )


def main() -> int:
    executable = ROOT / "engine" / ("strata.exe" if sys.platform == "win32" else "strata")
    try:
        expected = verify_source_build(executable)
        if sys.platform == "win32":
            verify_windows_cuda_dll(executable)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Juud local build record matches source fingerprint ({expected}); opt-in flags may be enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
