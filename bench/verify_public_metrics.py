#!/usr/bin/env python3
"""Recalculate a public Strata/Juud paired summary without private output text."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics

METRICS = ("prefill_tok_s", "decode_tok_s", "client_ttft_s", "client_elapsed_s")
FLAGS = ("nonempty_output", "prompt_count_matches", "no_prefix_reuse", "full_output",
         "usage_count_matches", "valid_timing")


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-6)


def verify(directory: Path) -> None:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest-public.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (directory / "paired_metrics.jsonl").read_text(encoding="utf-8").splitlines()
            if line]
    cases = [f"code-{count}" for count in manifest["targets"]] + [f"korean-{manifest['ko_target']}"]
    pairs = manifest["pairs"]
    if len(rows) != 2 * pairs * len(cases) or len(rows) != summary["rows"]:
        raise ValueError("row count differs from manifest or summary")
    indexed = {}
    for row in rows:
        key = row["pair"], row["case"], row["engine"]
        if key in indexed or key[0] not in range(1, pairs + 1) or key[1] not in cases or key[2] not in ("A", "B"):
            raise ValueError(f"unexpected or duplicate row {key}")
        if row["valid"] is not True or any(row["flags"].get(name) is not True for name in FLAGS):
            raise ValueError(f"invalid public row {key}")
        if row["prompt_tokens"] != int(key[1].split("-")[1]) or row["reused_tokens"] != 0:
            raise ValueError(f"prompt count or cache reuse differs at {key}")
        if row["completion_tokens"] != manifest["max_tokens"]:
            raise ValueError(f"completion count differs at {key}")
        if not close(row["prefill_tok_s"], row["prompt_tokens"] * 1000.0 / row["prompt_ms"]):
            raise ValueError(f"prefill rate differs from timing at {key}")
        if not close(row["decode_tok_s"], row["completion_tokens"] * 1000.0 / row["decode_ms"]):
            raise ValueError(f"decode rate differs from timing at {key}")
        if row["client_ttft_s"] <= 0 or row["client_elapsed_s"] < row["client_ttft_s"]:
            raise ValueError(f"invalid client timing at {key}")
        for hash_name in ("request_sha256", "output_sha256"):
            value = row[hash_name]
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"invalid hash at {key}")
        indexed[key] = row

    for case in cases:
        if case not in summary["cases"] or summary["cases"][case]["valid_pairs"] != pairs:
            raise ValueError(f"summary pair count differs for {case}")
        paired = []
        for pair in range(1, pairs + 1):
            a, b = indexed[(pair, case, "A")], indexed[(pair, case, "B")]
            if a["request_sha256"] != b["request_sha256"]:
                raise ValueError(f"request hashes differ for {case} pair {pair}")
            paired.append((a, b))
        if summary["cases"][case]["same_output_pairs"] != sum(
            a["output_sha256"] == b["output_sha256"] for a, b in paired
        ):
            raise ValueError(f"output-match count differs for {case}")
        for metric in METRICS:
            recorded = summary["cases"][case]["metrics"][metric]
            for arm in ("A", "B"):
                values = [row[metric] for a, b in paired for row in ((a,) if arm == "A" else (b,))]
                if not close(statistics.median(values), recorded[arm]["median"]):
                    raise ValueError(f"{case} {metric} {arm} median differs")
            gains = [((b[metric] / a[metric] - 1.0) if metric.endswith("tok_s") else
                      (1.0 - b[metric] / a[metric])) * 100.0 for a, b in paired]
            if not close(statistics.median(gains), recorded["paired_juud_gain_percent"]["median"]):
                raise ValueError(f"{case} {metric} paired gain differs")
    print(f"Verified {len(rows)} public rows and {pairs * len(cases)} A/B pairs: {directory}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    verify(args.directory)


if __name__ == "__main__":
    main()
