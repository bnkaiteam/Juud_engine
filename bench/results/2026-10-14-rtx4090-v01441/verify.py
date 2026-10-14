"""Recompute public A/B summaries from the privacy-reduced paired metrics."""

import json
import math
import re
import statistics
from pathlib import Path


data = json.loads((Path(__file__).parent / "pairs.json").read_text(encoding="utf-8"))
assert data["schema_version"] == 1
for series in data["series"]:
    records = series["records"]
    assert len(records) == 2 * series["pairs_requested"]
    for case in sorted({r["case"] for r in records}):
        rows = sorted((r for r in records if r["case"] == case), key=lambda r: r["pair"])
        assert [r["pair"] for r in rows] == list(range(1, series["pairs_requested"] + 1))
        assert all(r["both_valid"] for r in rows)
        assert all(re.fullmatch(r"[0-9a-f]{64}", r[key]) for r in rows for key in
                   ("request_sha256_A", "request_sha256_B", "output_sha256_A", "output_sha256_B"))
        assert all(r["request_sha256_A"] == r["request_sha256_B"] for r in rows)
        assert all(r["same_output"] == (r["output_sha256_A"] == r["output_sha256_B"])
                   for r in rows)
        assert all(r["prompt_tokens_A"] == r["prompt_tokens_B"] for r in rows)
        assert all(r["output_tokens_A"] == r["output_tokens_B"] == series["max_output_tokens"]
                   for r in rows)
        summary = series["summary"][case]
        decode = statistics.geometric_mean(r["decode_tok_s_B"] / r["decode_tok_s_A"] for r in rows)
        client = statistics.geometric_mean(
            r["client_elapsed_s_A"] / r["client_elapsed_s_B"] for r in rows)
        same = sum(r["same_output"] for r in rows)
        assert summary["valid_pairs"] == len(rows)
        assert summary["same_output_pairs"] == same
        assert math.isclose(summary["geometric_mean_decode_B_over_A"], decode, rel_tol=1e-12)
        assert math.isclose(summary["geometric_mean_client_time_A_over_B"], client, rel_tol=1e-12)
        print(f"{series['name']} {case}: {len(rows)} valid, {same} same output, "
              f"decode B/A {decode:.3f}, client time A/B {client:.3f}")
