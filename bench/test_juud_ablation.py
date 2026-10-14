#!/usr/bin/env python3
"""No-GPU checks for explicit option states and A/B report labels."""

import json
import tempfile
import unittest
from pathlib import Path

from juud_ablation import (CONTROLLED_ENV, STATES, check_request_parity, comparison_order,
                           launch_with_options, reject_saved_env_collisions,
                           require_direct_server_launch)
from juud_compare import summarize, validate_same_build_ablation


class JuudAblationTests(unittest.TestCase):
    def setUp(self):
        self.launch = {"command": ["python", "serve/server.py"], "cwd": "C:/juud",
                       "url": "http://127.0.0.1:18080",
                       "env": {"OTHER": "kept", "STRATA_POOL_SPIN_US": "5000",
                               "JUUD_POOL_ADAPTIVE_SPIN": "1", "JUUD_SKIP_UNUSED_ACTQ": "1"}}

    def test_all_option_states_explicit_and_other_environment_preserved(self):
        self.launch["env"]["juud_pool_adaptive_spin"] = "1"
        self.launch["env"]["juud_require_source_build"] = "1"
        base = launch_with_options(self.launch, "00")
        self.assertEqual(base["env"]["OTHER"], "kept")
        self.assertIsNone(base["env"]["STRATA_POOL_SPIN_US"])
        self.assertIsNone(base["env"]["JUUD_REQUIRE_SOURCE_BUILD"])
        self.assertNotIn("juud_pool_adaptive_spin", base["env"])
        self.assertNotIn("juud_require_source_build", base["env"])
        for state in STATES[1:]:
            variant = launch_with_options(self.launch, state)
            validate_same_build_ablation(base, variant)
            self.assertEqual(variant["env"]["JUUD_POOL_ADAPTIVE_SPIN"], state[0])
            self.assertEqual(variant["env"]["JUUD_SKIP_UNUSED_ACTQ"], state[1])
        self.assertEqual(self.launch["env"]["STRATA_POOL_SPIN_US"], "5000")

    def test_saved_config_cannot_shadow_ablation_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strata-iq3_s.json"
            for flag in CONTROLLED_ENV:
                path.write_text(json.dumps({"env": {flag.lower(): "1"}}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "saved env overrides ablation-controlled"):
                    reject_saved_env_collisions(path)
            path.write_text(json.dumps({"env": {"UNRELATED": "1"}}), encoding="utf-8")
            reject_saved_env_collisions(path)

    def test_wrapper_that_rewrites_flags_is_rejected(self):
        require_direct_server_launch(self.launch)
        wrapped = dict(self.launch, command=["RUN-JUUD.bat", "serve/server.py", "--config", "model.json"])
        with self.assertRaisesRegex(ValueError, "direct Python"):
            require_direct_server_launch(wrapped)

    def test_same_build_guard_rejects_confounded_or_identical_arms(self):
        base = launch_with_options(self.launch, "00")
        with self.assertRaisesRegex(ValueError, "at least one"):
            validate_same_build_ablation(base, launch_with_options(self.launch, "00"))
        variant = launch_with_options(self.launch, "10")
        variant["env"]["OTHER"] = "changed"
        with self.assertRaisesRegex(ValueError, "beyond"):
            validate_same_build_ablation(base, variant)
        variant = launch_with_options(self.launch, "10")
        variant["env"]["STRATA_POOL_SPIN_US"] = "100"
        with self.assertRaisesRegex(ValueError, "explicitly unset"):
            validate_same_build_ablation(base, variant)

    def test_order_has_each_state_once_and_is_reproducible(self):
        first = comparison_order(123)
        self.assertEqual(set(first), set(STATES))
        self.assertEqual(first, comparison_order(123))

    def test_cross_batch_request_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for state in STATES:
                path = out / state / "requests" / "pair-001.json"
                path.parent.mkdir(parents=True)
                digest = "different" if state == "01" else "same"
                path.write_text(json.dumps([{"case": "code-4096", "request_sha256": digest}]),
                                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Juud 00 and 01"):
                check_request_parity(out, 1)

    def test_summary_uses_ablation_labels_and_B_relative_gain(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "manifest.json").write_text(json.dumps({"A_label": "Juud 00",
                                                              "B_label": "Juud 10"}), encoding="utf-8")
            rows = []
            for arm, speed in (("A", 100.0), ("B", 110.0)):
                rows.append({"pair": 1, "case": "code-4096", "engine": arm,
                             "request_sha256": "same-input", "output_sha256": "same-output",
                             "valid": True, "prefill_tok_s": 200.0,
                             "decode_tok_s": speed, "client_ttft_s": 1.0,
                             "client_elapsed_s": 2.0})
            (out / "runs.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n",
                                            encoding="utf-8")
            summary = summarize(out)
            self.assertEqual((summary["A_label"], summary["B_label"]), ("Juud 00", "Juud 10"))
            measured = summary["cases"]["code-4096"]["metrics"]["decode_tok_s"]
            self.assertAlmostEqual(measured["paired_B_gain_percent"]["median"], 10.0)
            self.assertIn("B = Juud 10", (out / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
