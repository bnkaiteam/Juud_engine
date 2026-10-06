#!/usr/bin/env python3
"""Paired, serial Strata/Juud benchmark for a shared Qwen3.8-Flash-Next pack.

Run ``python bench/juud_compare.py --help`` for the two subcommands. No model is
downloaded or started until ``run`` is invoked with explicit launch configs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone


GPU_QUERY = "timestamp,index,utilization.gpu,clocks.sm,power.draw,temperature.gpu,memory.used"
GPU_FIELDS = ("gpu_index", "utilization_gpu_percent", "clocks_sm_mhz", "power_w",
              "temperature_c", "memory_used_mib")


def utc_from_ns(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000_000, timezone.utc).isoformat()


def gpu_number(raw: str) -> float | None:
    try:
        number = float(raw.strip())
        return number if math.isfinite(number) else None
    except ValueError:
        return None


class GpuSampler:
    """Capture independent nvidia-smi polls while one engine is running."""

    def __init__(self, path: Path, interval_s: float, executable: str, engine_pid: int):
        self.path = path
        self.interval_s = interval_s
        self.executable = executable
        self.engine_pid = engine_pid
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.samples: list[dict] = []
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.thread = threading.Thread(target=self._loop, name=f"gpu-sampler-{self.engine_pid}", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                print(f"GPU sampler did not stop promptly; inspect {self.path}", file=sys.stderr)

    def _loop(self) -> None:
        try:
            with self.path.open("w", encoding="utf-8", buffering=1) as stream:
                consecutive_errors = 0
                while not self.stop_event.is_set():
                    started_ns = time.time_ns()
                    try:
                        result = subprocess.run(
                            [self.executable, f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10, check=True,
                        )
                        finished_ns = time.time_ns()
                        lines = list(csv.reader(result.stdout.splitlines()))
                        if not lines:
                            raise ValueError("nvidia-smi returned no GPU rows")
                        for fields in lines:
                            if len(fields) != 7:
                                raise ValueError(f"expected 7 CSV fields, received {len(fields)}: {fields!r}")
                            values = [gpu_number(value) for value in fields[1:]]
                            if values[0] is None:
                                raise ValueError(f"invalid GPU index: {fields[1]!r}")
                            record = {"type": "sample", "engine_pid": self.engine_pid,
                                      "poll_started_unix_ns": started_ns,
                                      "poll_finished_unix_ns": finished_ns,
                                      "sample_unix_ns": (started_ns + finished_ns) // 2,
                                      "sample_utc": utc_from_ns((started_ns + finished_ns) // 2),
                                      "nvidia_timestamp": fields[0].strip(),
                                      "gpu_index": int(values[0]),
                                      **dict(zip(GPU_FIELDS[1:], values[1:])),
                                      "raw_csv_fields": [field.strip() for field in fields]}
                            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                            with self.lock:
                                self.samples.append(record)
                        consecutive_errors = 0
                    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
                        consecutive_errors += 1
                        detail = f"{type(exc).__name__}: {exc}"
                        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                            detail += f"; stderr: {exc.stderr.strip()[:1000]}"
                        record = {"type": "error", "engine_pid": self.engine_pid,
                                  "at_unix_ns": time.time_ns(), "message": detail,
                                  "consecutive_errors": consecutive_errors}
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                        print(f"GPU sampler error ({self.path}): {record['message']}", file=sys.stderr)
                        if consecutive_errors >= 3 or isinstance(exc, FileNotFoundError):
                            break
                    self.stop_event.wait(self.interval_s)
        except OSError as exc:
            print(f"GPU sampler could not write {self.path}: {exc}", file=sys.stderr)

    def for_window(self, start_ns: int, end_ns: int) -> dict:
        """Summarize polls whose timing interval overlaps this request interval."""
        with self.lock:
            matches = [sample for sample in self.samples
                       if sample["poll_started_unix_ns"] <= end_ns and
                       sample["poll_finished_unix_ns"] >= start_ns]
        by_gpu: dict[str, dict] = {}
        for gpu_index in sorted({sample["gpu_index"] for sample in matches}):
            gpu = [sample for sample in matches if sample["gpu_index"] == gpu_index]
            metrics = {}
            for field in GPU_FIELDS[1:]:
                values = [float(sample[field]) for sample in gpu if sample[field] is not None]
                metrics[field] = ({"mean": statistics.mean(values), "min": min(values), "max": max(values)}
                                  if values else None)
            by_gpu[str(gpu_index)] = {"samples": len(gpu), "metrics": metrics}
        return {"sample_count": len(matches), "by_gpu": by_gpu}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_json(url: str, timeout: float = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def request_bytes(request: dict) -> bytes:
    return json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_state(cwd: str) -> dict:
    prefix = ["git", "-c", f"safe.directory={Path(cwd).resolve().as_posix()}", "-C", cwd]
    try:
        sha = subprocess.run(prefix + ["rev-parse", "HEAD"], capture_output=True, text=True,
                             check=True, timeout=10).stdout.strip()
        dirty = bool(subprocess.run(prefix + ["status", "--porcelain"], capture_output=True, text=True,
                                    check=True, timeout=10).stdout.strip())
        return {"commit": sha, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def make_counter(root: Path, pack: Path):
    """Use Strata's own chat template/tokenizer, as its community harness does."""
    sys.path[:0] = [str(root.resolve()), str((root / "tools").resolve())]
    from strata_tokenizer import Tokenizer
    from serve.frontend import ChatTemplate, openai_to_messages

    directory = pack / "tokenizer"
    vocab = json.loads((directory / "vocab.json").read_text(encoding="utf-8"))
    tokens = [None] * len(vocab)
    for token, number in vocab.items():
        tokens[number] = token
    tokenizer = Tokenizer(tokens, (directory / "merges.txt").read_text(encoding="utf-8").splitlines(),
                          json.loads((directory / "token_type.json").read_text(encoding="utf-8")))
    template = ChatTemplate(directory / "chat_template.jinja")

    def count(request: dict) -> int:
        messages, tools, kwargs = openai_to_messages(request)
        rendered = template.render(messages, tools, **kwargs)
        return len(tokenizer.encode(rendered, parse_special=True))

    return count


def make_request(content: str, max_tokens: int) -> dict:
    return {"model": "strata", "messages": [{"role": "user", "content": content}],
            "temperature": 0, "reasoning_effort": "none", "max_tokens": max_tokens,
            "stream": True, "stream_options": {"include_usage": True}}


def fitted_request(prefix: str, filler: str, ending: str, target: int, max_tokens: int, count) -> tuple[dict, int]:
    low, high = 0, len(filler)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = make_request(prefix + filler[:middle] + ending, max_tokens)
        if count(candidate) <= target:
            low = middle
        else:
            high = middle - 1
    request = make_request(prefix + filler[:low] + ending, max_tokens)
    actual = count(request)
    if not target - 20 <= actual <= target:
        raise ValueError(f"could not fit {target} prompt tokens; got {actual}")
    return request, actual


def make_cases(pair: int, targets: list[int], ko_target: int, max_tokens: int, count) -> list[dict]:
    # The nonce is close to the start so another trial cannot reuse a long prefix.
    code = "\n".join(f"def task_{i:05d}(value: int) -> int: return (value * {(i % 97) + 1} + {i}) % 100003"
                     for i in range(12000))
    korean = "\n".join(f"회의 기록 {i:05d}: 담당자는 목표 {i % 71}와 일정 {i % 29}를 검토하고 다음 작업을 적었다."
                       for i in range(3000))
    cases = []
    for target in targets:
        prefix = f"Benchmark nonce: code-{target}-pair-{pair:04d}.\nReview this synthetic Python module:\n"
        ending = ("\n\nExplain the code in detail, including integer transforms, modulo arithmetic, "
                  "tests, complexity, and maintainability. Write at least 600 words.")
        req, actual = fitted_request(prefix, code, ending, target, max_tokens, count)
        cases.append({"case": f"code-{target}", "target_prompt_tokens": target,
                      "expected_prompt_tokens": actual, "request": req,
                      "request_sha256": sha256(request_bytes(req))})
    prefix = f"Benchmark nonce: korean-pair-{pair:04d}.\n다음은 가상의 프로젝트 회의 기록입니다.\n"
    ending = ("\n\n위 기록의 반복 패턴과 일정 관리상 문제를 한국어로 자세히 분석하고, "
              "개선 방안을 다섯 가지 이상 설명하세요. 답변은 800자 이상으로 작성하세요.")
    req, actual = fitted_request(prefix, korean, ending, ko_target, max_tokens, count)
    cases.append({"case": f"korean-{ko_target}", "target_prompt_tokens": ko_target,
                  "expected_prompt_tokens": actual, "request": req,
                  "request_sha256": sha256(request_bytes(req))})
    return cases


def load_launch(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    command = config.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise ValueError(f"{path}: command must be a nonempty JSON string array")
    cwd = Path(config.get("cwd", ""))
    if not cwd.is_dir():
        raise ValueError(f"{path}: cwd does not exist: {cwd}")
    url = config.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path not in ("", "/"):
        raise ValueError(f"{path}: url must be a loopback HTTP origin, e.g. http://127.0.0.1:18080")
    if not isinstance(config.get("env", {}), dict):
        raise ValueError(f"{path}: env must be a JSON object")
    config["cwd"] = str(cwd.resolve())
    config["url"] = url.rstrip("/")
    return config


def engine_config(launch: dict, pack: Path) -> tuple[dict, dict]:
    """Load and normalize the two setup configs so only the engine build differs."""
    command = launch["command"]
    if "--config" not in command or command.index("--config") + 1 >= len(command):
        raise ValueError("launch command must include --config <strata-iq3_s.json>")
    config_path = Path(command[command.index("--config") + 1])
    if not config_path.is_absolute():
        config_path = Path(launch["cwd"]) / config_path
    config_path = config_path.resolve()
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    def config_file(value: str) -> Path:
        path = Path(value)
        return (path if path.is_absolute() else config_path.parent / path).resolve()

    if not isinstance(cfg.get("args"), list) or not cfg.get("exe"):
        raise ValueError(f"{config_path}: missing engine args or exe")
    args = [str(x) for x in cfg["args"]]
    expected_pack = str(pack.resolve()).casefold()
    expected_tokenizer = str((pack / "tokenizer").resolve()).casefold()
    if "--pack" not in args or args.index("--pack") + 1 >= len(args):
        raise ValueError(f"{config_path}: engine args have no --pack")
    if str(config_file(args[args.index("--pack") + 1])).casefold() != expected_pack:
        raise ValueError(f"{config_path}: --pack differs from benchmark --pack")
    if str(config_file(cfg.get("tokenizer", ""))).casefold() != expected_tokenizer:
        raise ValueError(f"{config_path}: tokenizer differs from shared pack/tokenizer")
    if "--control-vector-scaled" in args:
        raise ValueError(f"{config_path}: experimental speed projection must be off for this comparison")
    canonical_args = []
    path_flags = {"--pack", "--native", "--ple-gguf", "--mtp", "--expert-profile"}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in path_flags:
            if i + 1 >= len(args):
                raise ValueError(f"{config_path}: {arg} has no value")
            path = config_file(args[i + 1])
            if arg == "--expert-profile":
                value = "sha256:" + sha256(path.read_bytes())
            else:
                value = str(path).casefold()
            canonical_args.extend((arg, value))
            i += 2
        else:
            canonical_args.append(arg)
            i += 1
    comparison = dict(cfg)
    for different_by_build in ("exe", "cwd", "log", "lib_dirs"):
        comparison.pop(different_by_build, None)
    comparison["args"] = canonical_args
    comparison["tokenizer"] = expected_tokenizer
    # Text-only benchmarking: vision reserves VRAM even without an image.
    if comparison.get("vision"):
        raise ValueError(f"{config_path}: turn vision off in both configurations for this benchmark")
    if comparison.get("effort_position", "start") != "start":
        raise ValueError(f"{config_path}: prompt counts require effort_position=start")
    return comparison, {"path": str(config_path), "sha256": sha256(config_path.read_bytes()),
                        "exe": str(config_file(cfg["exe"])), "max_context_config":
                        int(args[args.index("--max-context") + 1]) if "--max-context" in args else None}


def compare_engine_configs(a: dict, b: dict, pack: Path, required_context: int) -> dict:
    a_comparable, a_info = engine_config(a, pack)
    b_comparable, b_info = engine_config(b, pack)
    if a_info["exe"].casefold() == b_info["exe"].casefold():
        raise ValueError("A and B point to the same engine executable; this would not compare two builds")
    if a_comparable != b_comparable:
        keys = sorted(k for k in set(a_comparable) | set(b_comparable)
                      if a_comparable.get(k) != b_comparable.get(k))
        raise ValueError("A/B engine configurations differ in: " + ", ".join(keys) +
                         "; use equal model, tokenizer and inference settings")
    for label, info in (("A", a_info), ("B", b_info)):
        if info["max_context_config"] is None or info["max_context_config"] < required_context:
            raise ValueError(f"{label} config context {info['max_context_config']} is below required "
                             f"{required_context} tokens (prompt + output cap + 8)")
    return {"A": a_info, "B": b_info, "normalized_inference_config_sha256":
            sha256(json.dumps(a_comparable, sort_keys=True, ensure_ascii=False).encode("utf-8"))}


def wait_ready(proc: subprocess.Popen, url: str, timeout_s: float) -> tuple[float, dict]:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_s:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited during startup with code {proc.returncode}")
        try:
            health = get_json(url + "/health", timeout=2)
            if health.get("loaded") is True:
                return time.perf_counter() - started, health
        except (OSError, ValueError, urllib.error.HTTPError):
            pass
        time.sleep(1)
    raise TimeoutError(f"server did not report loaded=true within {timeout_s:g} seconds")


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.wait(timeout=45)
            return
        except (OSError, subprocess.TimeoutExpired):
            # Only the process tree created by this harness is targeted.
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=45)
            return
        except (OSError, subprocess.TimeoutExpired):
            os.killpg(proc.pid, signal.SIGKILL)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def one_request(url: str, case: dict, pair: int, engine_name: str, timeout_s: float) -> dict:
    body = request_bytes(case["request"])
    before = get_json(url + "/metrics")
    prior_requests = before.get("totals", {}).get("requests", 0)
    result = {"pair": pair, "engine": engine_name, "case": case["case"],
              "target_prompt_tokens": case["target_prompt_tokens"],
              "expected_prompt_tokens": case["expected_prompt_tokens"],
              "request_sha256": sha256(body), "max_tokens": case["request"]["max_tokens"]}
    chunks, texts, first, finish, error = [], [], None, None, None
    request_start_unix_ns = time.time_ns()
    started = time.perf_counter()
    wire = urllib.request.Request(url + "/v1/chat/completions", data=body,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(wire, timeout=timeout_s) as response:
            for line in response:
                if not line.startswith(b"data:"):
                    continue  # keep-alives and empty SSE lines are not generated tokens
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                chunk = json.loads(payload)
                chunks.append(chunk)
                if "error" in chunk:
                    error = chunk["error"]
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    text = (delta.get("content") or "") + (delta.get("reasoning_content") or "")
                    if text:
                        if first is None:
                            first = time.perf_counter() - started
                        texts.append(text)
                    finish = choice.get("finish_reason") or finish
    except urllib.error.HTTPError as exc:
        error = {"http_status": exc.code, "body": exc.read().decode("utf-8", errors="replace")[:2000]}
    except (OSError, ValueError, TimeoutError) as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    elapsed = time.perf_counter() - started
    request_end_unix_ns = time.time_ns()
    try:
        deadline = time.perf_counter() + 10
        while True:
            metrics = get_json(url + "/metrics")
            if metrics.get("totals", {}).get("requests", 0) > prior_requests:
                break
            if time.perf_counter() >= deadline:
                raise TimeoutError("no completed request appeared in /metrics")
            time.sleep(0.1)
        engine = (metrics.get("requests") or [{}])[0]
    except (OSError, ValueError, TimeoutError) as exc:
        metrics = {}
        engine = {}
        error = error or {"metrics_error": str(exc)}
    usage = next((chunk["usage"] for chunk in reversed(chunks) if "usage" in chunk), {})
    generated = engine.get("engine_generated")
    prompt_tokens = engine.get("prompt_tokens")
    reused = engine.get("reused")
    prompt_ms = engine.get("prompt_ms")
    decode_ms = engine.get("decode_ms")
    flags = {
        "nonempty_output": bool(texts),
        "prompt_count_matches": prompt_tokens == case["expected_prompt_tokens"],
        "no_prefix_reuse": reused == 0,
        "full_output": generated == case["request"]["max_tokens"] and finish == "length",
        "usage_count_matches": usage.get("prompt_tokens") == prompt_tokens and
        usage.get("completion_tokens") == generated,
        "valid_timing": isinstance(prompt_ms, (int, float)) and prompt_ms > 0 and
        isinstance(decode_ms, (int, float)) and decode_ms > 0,
    }
    result.update({"client_ttft_s": first, "client_elapsed_s": elapsed, "finish_reason": finish,
                   "request_window": {"start_unix_ns": request_start_unix_ns,
                                      "end_unix_ns": request_end_unix_ns,
                                      "start_utc": utc_from_ns(request_start_unix_ns),
                                      "end_utc": utc_from_ns(request_end_unix_ns)},
                   "usage": usage, "engine_metrics": engine, "output_text": "".join(texts),
                   "server_hardware_snapshot": metrics.get("hardware"),
                   "server_hardware_static": metrics.get("hardware_static"),
                   "output_sha256": sha256("".join(texts).encode("utf-8")),
                   "chunks": chunks, "flags": flags, "error": error,
                   "valid": error is None and first is not None and all(flags.values())})
    if flags["valid_timing"] and isinstance(prompt_tokens, int) and isinstance(reused, int):
        result["prefill_tok_s"] = (prompt_tokens - reused) / (prompt_ms / 1000)
        result["decode_tok_s"] = generated / (decode_ms / 1000) if isinstance(generated, int) else None
    return result


def attach_gpu_sampling(row: dict, sampler: GpuSampler | None, out: Path) -> None:
    if sampler is None:
        return
    window = row["request_window"]
    row["gpu_sampling"] = {
        "file": sampler.path.relative_to(out).as_posix(),
        "interval_s": sampler.interval_s,
        "window_match": "nvidia-smi poll interval overlaps request window",
        **sampler.for_window(window["start_unix_ns"], window["end_unix_ns"]),
    }


def median_range(values: list[float]) -> dict | None:
    return {"median": statistics.median(values), "min": min(values), "max": max(values)} if values else None


def summarize(out: Path) -> dict:
    rows_file = out / "runs.jsonl"
    rows = [json.loads(line) for line in rows_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    lookup = {(row["pair"], row["case"], row["engine"]): row for row in rows}
    cases = sorted({row["case"] for row in rows})
    summary = {"source": str(rows_file), "rows": len(rows), "cases": {}}
    for case in cases:
        pairs = sorted({row["pair"] for row in rows if row["case"] == case})
        valid = []
        for pair in pairs:
            a, b = lookup.get((pair, case, "A")), lookup.get((pair, case, "B"))
            if a and b and a.get("valid") and b.get("valid") and a["request_sha256"] == b["request_sha256"]:
                valid.append((a, b))
        report = {"attempted_pairs": len(pairs), "valid_pairs": len(valid),
                  "invalid_or_incomplete_pairs": len(pairs) - len(valid), "metrics": {},
                  "same_output_pairs": sum(a["output_sha256"] == b["output_sha256"] for a, b in valid)}
        for key in ("prefill_tok_s", "decode_tok_s", "client_ttft_s", "client_elapsed_s"):
            filtered = [(float(a[key]), float(b[key])) for a, b in valid
                        if isinstance(a.get(key), (int, float)) and isinstance(b.get(key), (int, float))
                        and a[key] > 0 and b[key] > 0]
            speed_higher_is_better = key.endswith("tok_s")
            gains = [(b / a - 1) * 100 if speed_higher_is_better else (1 - b / a) * 100
                     for a, b in filtered]
            report["metrics"][key] = {
                "A": median_range([a for a, _ in filtered]),
                "B": median_range([b for _, b in filtered]),
                "paired_juud_gain_percent": median_range(gains),
                "paired_gains_percent": gains,
            }
        summary["cases"][case] = report
    write_json(out / "summary.json", summary)
    lines = ["# Paired RTX benchmark summary", "", "A = Strata; B = Juud_engine. Positive gain means Juud is faster.",
             "Model startup is excluded from request timing. Invalid or incomplete pairs are excluded from medians.", "",
             "| Workload | Valid pairs | Prefill tok/s A → B | Decode tok/s A → B | TTFT s A → B | Total s A → B | Paired gains (prefill / decode / TTFT / total) |",
             "| --- | ---: | --- | --- | --- | --- | --- |"]
    def cell(metric: dict) -> str:
        a, b = metric["A"], metric["B"]
        return f"{a['median']:.2f} → {b['median']:.2f}" if a and b else "not measured"
    for case, report in summary["cases"].items():
        m = report["metrics"]
        keys = ("prefill_tok_s", "decode_tok_s", "client_ttft_s", "client_elapsed_s")
        gains = [f"{m[k]['paired_juud_gain_percent']['median']:+.1f}%" if m[k]["paired_juud_gain_percent"]
                 else "n/a" for k in keys]
        lines.append(f"| {case} | {report['valid_pairs']}/{report['attempted_pairs']} | "
                     f"{cell(m[keys[0]])} | {cell(m[keys[1]])} | {cell(m[keys[2]])} | "
                     f"{cell(m[keys[3]])} | {' / '.join(gains)} |")
    lines += ["", "Each request and engine timing record is in `runs.jsonl`. Inspect output text, draft acceptance, "
              "cache hits, failures and hardware logs before making a general performance claim.", ""]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def run(args: argparse.Namespace) -> None:
    if args.pairs < 1 or args.max_tokens < 1:
        raise ValueError("pairs and max-tokens must be positive")
    if args.gpu_sample_interval < 0:
        raise ValueError("gpu-sample-interval must be nonnegative (0 disables sampling)")
    targets = [int(x) for x in args.targets.split(",")]
    if not targets or any(x < 256 for x in targets) or args.ko_target < 256:
        raise ValueError("all prompt targets must be at least 256")
    a, b = load_launch(args.a), load_launch(args.b)
    if a["url"] != b["url"]:
        raise ValueError("A and B must use the same loopback URL because only one server runs at a time")
    required_context = max([*targets, args.ko_target]) + args.max_tokens + 8
    config_check = compare_engine_configs(a, b, args.pack, required_context)
    try:
        get_json(a["url"] + "/health", timeout=2)
    except (OSError, ValueError, urllib.error.HTTPError):
        pass
    else:
        raise RuntimeError(f"a server already answers on {a['url']}; stop it before this serial benchmark")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "runs.jsonl").exists():
        raise FileExistsError(f"{out / 'runs.jsonl'} already exists; use a new output directory")
    count = make_counter(args.root, args.pack)
    write_json(out / "manifest.json", {"started_utc": datetime.now(timezone.utc).isoformat(),
                                        "host": platform.platform(), "python": sys.version,
                                        "pairs": args.pairs, "targets": targets, "ko_target": args.ko_target,
                                        "max_tokens": args.max_tokens, "root": str(args.root.resolve()),
                                        "pack": str(args.pack.resolve()),
                                        "A_launch_config": str(args.a.resolve()), "B_launch_config": str(args.b.resolve()),
                                        "A_config_sha256": sha256(args.a.read_bytes()),
                                        "B_config_sha256": sha256(args.b.read_bytes()),
                                        "inference_config_check": config_check,
                                        "required_context": required_context,
                                        "gpu_sampling": {"enabled": args.gpu_sample_interval > 0,
                                                         "interval_s": args.gpu_sample_interval,
                                                         "executable": args.nvidia_smi,
                                                         "query": GPU_QUERY},
                                        "A_source": source_state(a["cwd"]), "B_source": source_state(b["cwd"]),
                                        "order": "A,B then B,A, repeated; each launch receives one warm-up"})
    with (out / "runs.jsonl").open("a", encoding="utf-8") as stream:
        for pair in range(1, args.pairs + 1):
            cases = make_cases(pair, targets, args.ko_target, args.max_tokens, count)
            write_json(out / "requests" / f"pair-{pair:03d}.json", cases)
            for engine_name in (("A", "B") if pair % 2 else ("B", "A")):
                cfg = a if engine_name == "A" else b
                log_path = out / "server-logs" / f"pair-{pair:03d}-{engine_name}.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"pair {pair}/{args.pairs}: starting {engine_name}", flush=True)
                with log_path.open("wb") as log:
                    env = os.environ.copy()
                    for key, value in cfg.get("env", {}).items():
                        if value is None:
                            env.pop(str(key), None)
                        else:
                            env[str(key)] = str(value)
                    popen_kwargs = {"cwd": cfg["cwd"], "env": env, "stdin": subprocess.DEVNULL,
                                    "stdout": log, "stderr": subprocess.STDOUT}
                    if os.name == "nt":
                        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                    else:
                        popen_kwargs["start_new_session"] = True
                    proc = subprocess.Popen(cfg["command"], **popen_kwargs)
                    sampler = None
                    if args.gpu_sample_interval > 0:
                        gpu_path = out / "gpu-samples" / f"pair-{pair:03d}-{engine_name}.jsonl"
                        try:
                            sampler = GpuSampler(gpu_path, args.gpu_sample_interval, args.nvidia_smi, proc.pid)
                            sampler.start()
                        except (OSError, RuntimeError) as exc:
                            sampler = None
                            print(f"GPU sampler failed to start ({gpu_path}): {exc}", file=sys.stderr)
                    try:
                        startup_s, health = wait_ready(proc, cfg["url"], args.startup_timeout)
                        expected_actual = max(c["expected_prompt_tokens"] for c in cases) + args.max_tokens + 8
                        reported_context = health.get("max_context")
                        if not isinstance(reported_context, int) or reported_context < expected_actual:
                            raise ValueError(f"{engine_name} /health max_context={reported_context} is below "
                                             f"the required {expected_actual} prompt + output + 8 tokens")
                        write_json(out / "server-logs" / f"pair-{pair:03d}-{engine_name}-health.json",
                                   {"startup_s": startup_s, "health": health})
                        warmup = {"case": "warmup", "target_prompt_tokens": None,
                                  "expected_prompt_tokens": count(make_request("Reply with exactly READY.", 16)),
                                  "request": make_request("Reply with exactly READY.", 16)}
                        warmup_row = one_request(cfg["url"], warmup, pair, engine_name, args.request_timeout)
                        attach_gpu_sampling(warmup_row, sampler, out)
                        write_json(out / "server-logs" / f"pair-{pair:03d}-{engine_name}-warmup.json", warmup_row)
                        warmup_flags = warmup_row["flags"]
                        required_warmup_flags = ("nonempty_output", "prompt_count_matches", "no_prefix_reuse",
                                                 "usage_count_matches", "valid_timing")
                        if warmup_row["error"] is not None or not all(warmup_flags[k] for k in required_warmup_flags):
                            raise RuntimeError(f"{engine_name} warmup failed or lacked measured output/timing: "
                                               f"error={warmup_row['error']}, flags={warmup_flags}")
                        for case in cases:
                            row = one_request(cfg["url"], case, pair, engine_name, args.request_timeout)
                            attach_gpu_sampling(row, sampler, out)
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                            stream.flush()
                            print(f"  {engine_name} {case['case']}: valid={row['valid']} "
                                  f"prefill={row.get('prefill_tok_s')} decode={row.get('decode_tok_s')}", flush=True)
                    finally:
                        try:
                            if sampler is not None:
                                sampler.stop()
                        finally:
                            stop_server(proc)
            summarize(out)
    print(f"Results: {out / 'summary.md'}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    runner = sub.add_parser("run", help="launch A and B serially, alternating order by pair")
    runner.add_argument("--a", type=Path, required=True, help="Strata launch JSON")
    runner.add_argument("--b", type=Path, required=True, help="Juud launch JSON")
    runner.add_argument("--root", type=Path, required=True, help="source root used only for the shared tokenizer")
    runner.add_argument("--pack", type=Path, required=True, help="shared IQ3_S pack directory")
    runner.add_argument("--out", type=Path, required=True, help="new output directory")
    runner.add_argument("--pairs", type=int, default=5)
    runner.add_argument("--targets", default="4096,32768,128000")
    runner.add_argument("--ko-target", type=int, default=2048)
    runner.add_argument("--max-tokens", type=int, default=256)
    runner.add_argument("--startup-timeout", type=float, default=600)
    runner.add_argument("--request-timeout", type=float, default=1800)
    runner.add_argument("--gpu-sample-interval", type=float, default=1.0,
                        help="nvidia-smi poll interval in seconds (default: 1; 0 disables)")
    runner.add_argument("--nvidia-smi", default="nvidia-smi",
                        help="nvidia-smi executable or full path (default: nvidia-smi)")
    summarizer = sub.add_parser("summarize", help="regenerate summary.json and summary.md from runs.jsonl")
    summarizer.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "run":
            run(args)
        else:
            summarize(args.out)
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
