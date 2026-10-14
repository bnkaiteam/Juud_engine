#!/usr/bin/env python3
"""Measure Strata against Juud 00, then isolate Juud's two opt-in switches.

The four comparisons are Strata versus Juud 00 and Juud 00 versus 10/01/11. Each uses
juud_compare.py's paired serial runner. No speed claim is made until the
resulting per-pair records have been inspected.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import subprocess
import sys
from pathlib import Path

from juud_compare import compare_engine_configs, engine_config, load_launch, validate_same_build_ablation


STATES = ("00", "10", "01", "11")
OPTIONS = ("JUUD_POOL_ADAPTIVE_SPIN", "JUUD_SKIP_UNUSED_ACTQ")
CONTROLLED_ENV = frozenset((*OPTIONS, "STRATA_POOL_SPIN_US", "JUUD_REQUIRE_SOURCE_BUILD"))


def launch_with_options(source: dict, state: str | None) -> dict:
    """Override inherited launch variables so each arm has a known state."""
    result = copy.deepcopy(source)
    env = result.setdefault("env", {})
    for key in list(env):
        if str(key).upper() in CONTROLLED_ENV:
            del env[key]
    env["STRATA_POOL_SPIN_US"] = None
    env["JUUD_REQUIRE_SOURCE_BUILD"] = None
    for index, option in enumerate(OPTIONS):
        env[option] = None if state is None else state[index]
    return result


def reject_saved_env_collisions(config_path: Path) -> None:
    """The server applies saved cfg.env after launch env, so deny shadowed flags."""
    saved = json.loads(config_path.read_text(encoding="utf-8-sig"))
    saved_env = saved.get("env") or {}
    if not isinstance(saved_env, dict):
        raise ValueError(f"{config_path}: saved env must be a JSON object")
    collisions = sorted(str(key) for key in saved_env if str(key).upper() in CONTROLLED_ENV)
    if collisions:
        raise ValueError(f"{config_path}: saved env overrides ablation-controlled flags: "
                         f"{', '.join(collisions)}; remove them from the saved config")


def require_direct_server_launch(launch: dict) -> None:
    """A wrapper such as RUN-JUUD can rewrite flags after this runner sets them."""
    command = launch["command"]
    executable = Path(command[0]).name.casefold()
    direct_server = any(part.replace("\\", "/").removeprefix("./").endswith("serve/server.py")
                        for part in command[1:])
    if not executable.startswith("python") or not direct_server:
        raise ValueError("ablation requires a direct Python serve/server.py launch, not a setup/start wrapper")


def comparison_order(seed: int) -> list[str]:
    order = list(STATES)
    random.Random(seed).shuffle(order)
    return order


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_request_parity(out: Path, pairs: int) -> None:
    """Verify every batch actually sent the same cases and exact request bytes."""
    for pair in range(1, pairs + 1):
        name = f"pair-{pair:03d}.json"
        reference = json.loads((out / "00" / "requests" / name).read_text(encoding="utf-8"))
        expected = [(case["case"], case["request_sha256"]) for case in reference]
        for state in STATES[1:]:
            actual = json.loads((out / state / "requests" / name).read_text(encoding="utf-8"))
            if [(case["case"], case["request_sha256"]) for case in actual] != expected:
                raise ValueError(f"request mismatch between Juud 00 and {state}, pair {pair}")


def assemble_report(out: Path, order: list[str], pairs: int) -> None:
    check_request_parity(out, pairs)
    all_summaries = {}
    lines = ["# Strata / Juud_engine option ablation", "",
             "These are four **separate** paired comparisons, run in the recorded order. "
             "A positive gain means B is faster than A within that comparison. "
             "The 10, 01 and 11 rows compare the same Juud executable against Juud 00; "
             "00 compares Juud with stock Strata. The request hashes were checked across all four "
             "batches. Do not subtract percentages across rows.", "",
             "State digits are `JUUD_POOL_ADAPTIVE_SPIN` and `JUUD_SKIP_UNUSED_ACTQ` respectively. "
             "`STRATA_POOL_SPIN_US` is explicitly unset in every arm. Each comparison alternates "
             "A/B launch order by pair and keeps the same requests within that pair.", "",
             f"Comparison order: {', '.join(order)}. Requested pairs per comparison: {pairs}.", "",
             "| Comparison | Workload | Valid pairs | Decode gain B vs A | Full latency gain B vs A | Same output |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for state in order:
        summary_path = out / state / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        all_summaries[state] = summary
        for case, report in summary["cases"].items():
            metrics = report["metrics"]
            def gain(key: str) -> str:
                measured = metrics[key]["paired_B_gain_percent"]
                return f"{measured['median']:+.1f}%" if measured else "n/a"
            lines.append(f"| {summary['A_label']} → {summary['B_label']} | {case} | "
                         f"{report['valid_pairs']}/{report['attempted_pairs']} | "
                         f"{gain('decode_tok_s')} | {gain('client_elapsed_s')} | "
                         f"{report['same_output_pairs']}/{report['valid_pairs']} |")
    lines.extend(["", "Source commits, launch hashes, exact requests, output text, engine timings and "
                  "GPU samples are in each comparison's manifest and raw files. Check output equality, "
                  "draft acceptance, clocks, errors and run order before interpreting gains. "
                  "The results apply only to the measured GPU, model, settings and prompts. "
                  "This script does not measure H100 or multi-user throughput.", ""])
    write_json(out / "ablation.json", {"order": order, "pairs_per_comparison": pairs,
                                         "summaries": all_summaries})
    (out / "ablation.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strata", type=Path, required=True, help="stock Strata launch JSON")
    parser.add_argument("--juud", type=Path, required=True, help="locally built Juud launch JSON")
    parser.add_argument("--root", type=Path, required=True, help="source root for the shared tokenizer")
    parser.add_argument("--pack", type=Path, required=True, help="shared model pack")
    parser.add_argument("--out", type=Path, required=True, help="new output directory outside the repository")
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261014,
                        help="records a reproducible shuffle of the four comparison batches")
    parser.add_argument("--targets", default="4096,32768,128000")
    parser.add_argument("--ko-target", type=int, default=2048)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--startup-timeout", type=float, default=600)
    parser.add_argument("--request-timeout", type=float, default=1800)
    parser.add_argument("--gpu-sample-interval", type=float, default=1.0)
    parser.add_argument("--nvidia-smi", default="nvidia-smi")
    parser.add_argument("--plan-only", action="store_true", help="validate and print the plan without launching")
    args = parser.parse_args()
    try:
        if args.pairs < 1 or args.max_tokens < 1 or args.ko_target < 256:
            raise ValueError("pairs and max/KO token counts must be positive and KO target at least 256")
        targets = [int(value) for value in args.targets.split(",")]
        if not targets or any(value < 256 for value in targets):
            raise ValueError("all prompt targets must be at least 256")
        if not args.root.is_dir() or not args.pack.is_dir():
            raise ValueError("the tokenizer source root and shared model pack must both exist")
        required_context = max([*targets, args.ko_target]) + args.max_tokens + 8
        stock = launch_with_options(load_launch(args.strata), None)
        juud_source = load_launch(args.juud)
        juud = {state: launch_with_options(juud_source, state) for state in STATES}
        for launch in (stock, juud["00"]):
            require_direct_server_launch(launch)
            _, info = engine_config(launch, args.pack)
            reject_saved_env_collisions(Path(info["path"]))
        if stock["url"] != juud["00"]["url"]:
            raise ValueError("stock and Juud must use the same loopback URL")
        stock_check = compare_engine_configs(stock, juud["00"], args.pack, required_context)
        for label in ("A", "B"):
            if not Path(stock_check[label]["exe"]).is_file():
                raise ValueError(f"{label} engine executable does not exist: {stock_check[label]['exe']}")
        for state in STATES[1:]:
            validate_same_build_ablation(juud["00"], juud[state])
            check = compare_engine_configs(juud["00"], juud[state], args.pack,
                                           required_context, allow_same_executable=True)
            if check["A"]["exe"].casefold() != check["B"]["exe"].casefold():
                raise ValueError("Juud variants must share one engine executable")
        order = comparison_order(args.seed)
        print("Comparison order: " + ", ".join(order), flush=True)
        if args.plan_only:
            return 0
        out = args.out.resolve()
        if out.exists():
            raise FileExistsError(f"output directory already exists: {out}")
        config_dir = out / "launch-configs"
        write_json(config_dir / "strata.json", stock)
        for state, launch in juud.items():
            write_json(config_dir / f"juud-{state}.json", launch)
        write_json(out / "plan.json", {"order": order, "pairs_per_comparison": args.pairs,
                                       "state_digits": list(OPTIONS),
                                       "stock_launch": str(args.strata.resolve()),
                                       "juud_launch": str(args.juud.resolve())})
        for state in order:
            baseline = state == "00"
            cmd = [sys.executable, str(Path(__file__).with_name("juud_compare.py")), "run",
                   "--a", str(config_dir / ("strata.json" if baseline else "juud-00.json")),
                   "--b", str(config_dir / f"juud-{state}.json"),
                   "--a-label", "Strata" if baseline else "Juud 00",
                   "--b-label", f"Juud {state}",
                   "--root", str(args.root), "--pack", str(args.pack),
                   "--out", str(out / state), "--pairs", str(args.pairs),
                   "--targets", args.targets, "--ko-target", str(args.ko_target),
                   "--max-tokens", str(args.max_tokens),
                   "--startup-timeout", str(args.startup_timeout),
                   "--request-timeout", str(args.request_timeout),
                   "--gpu-sample-interval", str(args.gpu_sample_interval),
                   "--nvidia-smi", args.nvidia_smi]
            if not baseline:
                cmd.append("--same-build-ablation")
            print(f"Running {('Strata' if baseline else 'Juud 00')} -> Juud {state}", flush=True)
            subprocess.run(cmd, check=True)
        assemble_report(out, order, args.pairs)
        print(f"Ablation report: {out / 'ablation.md'}", flush=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ablation error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
