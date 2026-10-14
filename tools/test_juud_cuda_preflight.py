"""The Windows Juud launcher reports a missing cuBLAS DLL before starting the engine.

These tests use fake DLL files and do not need CUDA or a GPU.

    python -m unittest tools.test_juud_cuda_preflight
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import check_juud_build


class WindowsCudaPreflight(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"
        self.engine.mkdir()
        self.executable = self.engine / "strata.exe"
        self.executable.write_bytes(b"test executable")

    def record(self, dirs: list[Path], toolkit: int = 13, backend: str = "cuda") -> None:
        (self.engine / "BUILD.json").write_text(
            json.dumps({"source": "local", "backend": backend, "toolkit": toolkit,
                        "cuda_dirs": [str(d) for d in dirs]}),
            encoding="utf-8",
        )

    def test_finds_dll_in_recorded_cuda_folder(self) -> None:
        cuda_bin = self.root / "CUDA 13" / "bin" / "x64"
        cuda_bin.mkdir(parents=True)
        (cuda_bin / "cublas64_13.dll").write_bytes(b"test DLL")
        self.record([cuda_bin])
        check_juud_build.verify_windows_cuda_dll(self.executable, {"PATH": ""})

    def test_finds_dll_in_inherited_path(self) -> None:
        cuda_bin = self.root / "CUDA on PATH"
        cuda_bin.mkdir()
        (cuda_bin / "cublas64_13.dll").write_bytes(b"test DLL")
        self.record([self.root / "recorded-but-missing"])
        check_juud_build.verify_windows_cuda_dll(
            self.executable, {"PATH": f"{self.root / 'other'};{cuda_bin}"}
        )

    def test_finds_dll_in_matching_model_config(self) -> None:
        cuda_bin = self.root / "custom CUDA folder"
        cuda_bin.mkdir()
        (cuda_bin / "cublas64_13.dll").write_bytes(b"test DLL")
        self.record([self.root / "recorded-but-missing"])
        (self.root / "strata-iq3_s.json").write_text(
            json.dumps({"exe": str(self.executable), "lib_dirs": [str(cuda_bin)]}), encoding="utf-8"
        )
        check_juud_build.verify_windows_cuda_dll(self.executable, {"PATH": ""})

    def test_saved_model_path_overrides_build_record_path(self) -> None:
        build_bin = self.root / "build CUDA folder"
        build_bin.mkdir()
        (build_bin / "cublas64_13.dll").write_bytes(b"test DLL")
        self.record([build_bin])
        (self.root / "strata-iq3_s.json").write_text(
            json.dumps({"exe": str(self.executable), "lib_dirs": [str(self.root / "missing")]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "cublas64_13.dll"):
            check_juud_build.verify_windows_cuda_dll(self.executable, {"PATH": ""})

    def test_missing_dll_names_a_specific_repair(self) -> None:
        self.record([self.root / "recorded-but-missing"])
        with self.assertRaisesRegex(ValueError, "cublas64_13.dll") as caught:
            check_juud_build.verify_windows_cuda_dll(self.executable, {"PATH": ""})
        self.assertIn("CUDA Toolkit 13.0", str(caught.exception))
        self.assertIn("strata-*.json lib_dirs", str(caught.exception))

    def test_cuda_12_build_checks_its_own_dll(self) -> None:
        cuda_bin = self.root / "CUDA 12"
        cuda_bin.mkdir()
        (cuda_bin / "cublas64_12.dll").write_bytes(b"test DLL")
        self.record([cuda_bin], toolkit=12)
        check_juud_build.verify_windows_cuda_dll(self.executable, {"PATH": ""})

    def test_non_cuda_build_needs_no_cublas(self) -> None:
        self.record([], backend="hip")
        check_juud_build.verify_windows_cuda_dll(self.executable, {"PATH": ""})


if __name__ == "__main__":
    unittest.main()
