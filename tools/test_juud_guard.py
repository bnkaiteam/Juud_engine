"""The Juud launcher must reject a prebuilt or stale engine record.

These tests use a temporary fake executable and do not need a GPU or model.

    python -m unittest tools.test_juud_guard
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import check_juud_build


class SourceBuildGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.executable = Path(self.temp.name) / "strata"
        self.executable.write_bytes(b"test executable")
        self.record = self.executable.parent / "BUILD.json"
        self.source_hash = mock.patch.object(check_juud_build.setup, "source_hash", return_value="current")
        self.source_hash.start()
        self.addCleanup(self.source_hash.stop)

    def write_record(self, **changes: str) -> None:
        metadata = {"source": "local", "src": "current", **changes}
        self.record.write_text(json.dumps(metadata), encoding="utf-8")

    def test_accepts_matching_local_source_build(self) -> None:
        self.write_record()
        self.assertEqual(check_juud_build.verify_source_build(self.executable), "current")

    def test_rejects_recorded_prebuilt(self) -> None:
        self.write_record(source="prebuilt")
        with self.assertRaisesRegex(ValueError, "Strata prebuilt"):
            check_juud_build.verify_source_build(self.executable)

    def test_rejects_stale_source(self) -> None:
        self.write_record(src="old")
        with self.assertRaisesRegex(ValueError, "older source"):
            check_juud_build.verify_source_build(self.executable)

    def test_rejects_missing_executable_even_with_valid_record(self) -> None:
        self.write_record()
        self.executable.unlink()
        with self.assertRaisesRegex(ValueError, "binary or build record is missing"):
            check_juud_build.verify_source_build(self.executable)

    def test_rejects_missing_or_invalid_record(self) -> None:
        with self.assertRaisesRegex(ValueError, "binary or build record is missing"):
            check_juud_build.verify_source_build(self.executable)
        self.record.write_text("{invalid", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cannot read engine build record"):
            check_juud_build.verify_source_build(self.executable)


if __name__ == "__main__":
    unittest.main()
