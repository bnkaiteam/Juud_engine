#!/usr/bin/env python3
"""Render an evidence-scoped Korean Strata/Juud comparison from a completed paired run.

This script never starts an engine. It refuses stale summaries and computes every displayed
performance value from the same valid A/B request pairs used by juud_compare.py.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

METRICS = ("prefill_tok_s", "decode_tok_s", "client_ttft_s", "client_elapsed_s")
REQUIRED_FLAGS = (
    "nonempty_output", "prompt_count_matches", "no_prefix_reuse",
    "full_output", "usage_count_matches", "valid_timing",
)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def positive(value) -> bool:
    return number(value) and value > 0


def near(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-7)


def valid_row(row: dict) -> tuple[bool, str, dict]:
    """Check raw evidence, rather than trusting a stored `valid` or throughput field."""
    if row.get("error") is not None:
        return False, "요청 오류", {}
    flags = row.get("flags") or {}
    missing_flags = [name for name in REQUIRED_FLAGS if flags.get(name) is not True]
    if missing_flags:
        return False, "검증 실패: " + ", ".join(missing_flags), {}
    if row.get("valid") is not True:
        return False, "러너 무효 판정", {}
    engine = row.get("engine_metrics") or {}
    usage = row.get("usage") or {}
    prompt, reused = engine.get("prompt_tokens"), engine.get("reused")
    generated, maximum = engine.get("engine_generated"), row.get("max_tokens")
    prompt_ms, decode_ms = engine.get("prompt_ms"), engine.get("decode_ms")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (prompt, reused, generated, maximum)):
        return False, "토큰 계수 누락", {}
    if not (prompt > reused >= 0 and maximum > 0 and generated == maximum and
            prompt == row.get("expected_prompt_tokens") and row.get("finish_reason") == "length"):
        return False, "출력 미완료 또는 프롬프트 불일치", {}
    if usage.get("prompt_tokens") != prompt or usage.get("completion_tokens") != generated:
        return False, "usage 토큰 계수 불일치", {}
    if reused != 0 or not positive(prompt_ms) or not positive(decode_ms):
        return False, "prefix 재사용 또는 엔진 시간 무효", {}
    ttft, elapsed = row.get("client_ttft_s"), row.get("client_elapsed_s")
    if not positive(ttft) or not positive(elapsed) or ttft > elapsed:
        return False, "클라이언트 시간 무효", {}
    output = row.get("output_text")
    if not isinstance(output, str) or not output:
        return False, "출력 텍스트 누락", {}
    if hashlib.sha256(output.encode("utf-8")).hexdigest() != row.get("output_sha256"):
        return False, "출력 해시 불일치", {}
    calculated = {
        "prefill_tok_s": (prompt - reused) / (prompt_ms / 1000.0),
        "decode_tok_s": generated / (decode_ms / 1000.0),
        "client_ttft_s": float(ttft),
        "client_elapsed_s": float(elapsed),
    }
    for metric in ("prefill_tok_s", "decode_tok_s"):
        stored = row.get(metric)
        if stored is not None and (not positive(stored) or not near(float(stored), calculated[metric])):
            return False, f"저장된 {metric} 값 불일치", {}
    return True, "", calculated


def expected_cases(manifest: dict) -> tuple[int, list[str]]:
    pairs, targets, ko = manifest.get("pairs"), manifest.get("targets"), manifest.get("ko_target")
    if not isinstance(pairs, int) or pairs < 1 or not isinstance(targets, list) or not targets:
        raise ValueError("manifest: invalid pairs or targets")
    if not all(isinstance(x, int) and x > 0 for x in targets) or not isinstance(ko, int) or ko < 1:
        raise ValueError("manifest: invalid prompt targets")
    names = [f"code-{x}" for x in targets] + [f"korean-{ko}"]
    if len(names) != len(set(names)):
        raise ValueError("manifest: duplicate cases")
    return pairs, names


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    return rows


def collect_pairs(rows: list[dict], manifest: dict) -> dict:
    pair_count, cases = expected_cases(manifest)
    index = {}
    for row in rows:
        key = (row.get("pair"), row.get("case"), row.get("engine"))
        if not isinstance(key[0], int) or not 1 <= key[0] <= pair_count or key[1] not in cases or key[2] not in ("A", "B"):
            raise ValueError(f"runs.jsonl: unexpected pair/case/engine {key!r}")
        if key in index:
            raise ValueError(f"runs.jsonl: duplicate row {key!r}")
        index[key] = row
    collected = {}
    for case in cases:
        valid = []
        failures = Counter()
        for pair in range(1, pair_count + 1):
            a, b = index.get((pair, case, "A")), index.get((pair, case, "B"))
            if a is None or b is None:
                failures["A/B 요청 기록 누락"] += 1
                continue
            a_ok, a_reason, a_metrics = valid_row(a)
            b_ok, b_reason, b_metrics = valid_row(b)
            if not a_ok or not b_ok:
                failures[" / ".join(x for x in (f"A {a_reason}" if not a_ok else "",
                                                 f"B {b_reason}" if not b_ok else "") if x)] += 1
                continue
            if a.get("request_sha256") != b.get("request_sha256") or not a.get("request_sha256"):
                failures["A/B 요청 해시 불일치"] += 1
                continue
            if (a.get("expected_prompt_tokens") != b.get("expected_prompt_tokens") or
                    a.get("max_tokens") != b.get("max_tokens")):
                failures["A/B 요청 크기 불일치"] += 1
                continue
            ast, bst = a.get("server_hardware_static") or {}, b.get("server_hardware_static") or {}
            if ast.get("gpu_name") and bst.get("gpu_name") and ast["gpu_name"] != bst["gpu_name"]:
                failures["A/B GPU 이름 불일치"] += 1
                continue
            valid.append((a, b, a_metrics, b_metrics))
        collected[case] = {"valid": valid, "failures": failures, "attempted": pair_count}
    return collected


def metrics_for(valid: list[tuple]) -> dict:
    result = {}
    for key in METRICS:
        aa = [am[key] for _, _, am, _ in valid]
        bb = [bm[key] for _, _, _, bm in valid]
        higher_is_better = key.endswith("tok_s")
        gains = [((b / a) - 1.0) * 100.0 if higher_is_better else (1.0 - b / a) * 100.0
                 for a, b in zip(aa, bb)]
        result[key] = {"A": statistics.median(aa) if aa else None,
                       "B": statistics.median(bb) if bb else None,
                       "gain": statistics.median(gains) if gains else None}
    return result


def check_summary(summary: dict, rows: list[dict], collected: dict) -> None:
    if summary.get("rows") != len(rows):
        raise ValueError("summary.json rows count differs from runs.jsonl")
    described = summary.get("cases") or {}
    if set(described) - set(collected):
        raise ValueError("summary.json contains unexpected cases")
    for case, data in collected.items():
        saved = described.get(case)
        if saved is None:
            if data["valid"]:
                raise ValueError(f"summary.json missing valid case {case}")
            continue
        if saved.get("valid_pairs") != len(data["valid"]):
            raise ValueError(f"summary.json has stale valid-pair count for {case}")
        if saved.get("same_output_pairs") != sum(a.get("output_sha256") == b.get("output_sha256")
                                                 for a, b, _, _ in data["valid"]):
            raise ValueError(f"summary.json has stale output-match count for {case}")
        measured = metrics_for(data["valid"])
        for key, values in measured.items():
            stored = (saved.get("metrics") or {}).get(key) or {}
            for name, field in (("A", "A"), ("B", "B"), ("gain", "paired_juud_gain_percent")):
                observed = (stored.get(field) or {}).get("median")
                expected = values[name]
                if expected is None:
                    if observed is not None:
                        raise ValueError(f"summary.json has unexpected {case}/{key}/{field}")
                elif not number(observed) or not near(float(observed), expected):
                    raise ValueError(f"summary.json has stale {case}/{key}/{field}")


def fmt_value(value: float | None, decimals: int = 2) -> str:
    return "측정 불가" if value is None else f"{value:,.{decimals}f}"


def fmt_gain(value: float | None) -> str:
    return "측정 불가" if value is None else f"{value:+.1f}%"


def mtp(valid: list[tuple], side: int) -> str:
    rows = [pair[side] for pair in valid]
    if not rows:
        return "측정 불가"
    counters = []
    for row in rows:
        engine = row.get("engine_metrics") or {}
        counters.append((engine.get("drafts_accepted"), engine.get("drafts_offered")))
    if any(not isinstance(a, int) or not isinstance(o, int) or a < 0 or o < a for a, o in counters):
        return "기록 불완전"
    accepted, offered = sum(a for a, _ in counters), sum(o for _, o in counters)
    return f"{accepted:,}/{offered:,} ({accepted / offered * 100:.1f}%)" if offered else "0/0 (수용률 계산 불가)"


def observed_range(valid: list[tuple], side: int, key: str, scale: float = 1.0, unit: str = "") -> str:
    values = []
    for pair in valid:
        snapshot = pair[side].get("server_hardware_snapshot") or {}
        value = snapshot.get(key)
        if number(value):
            values.append(float(value) / scale)
    if not values:
        return "기록 없음"
    return f"{min(values):.1f}–{max(values):.1f}{unit} ({len(values)}개 완료 시점)"


def safe_text(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else "기록 없음"


def launch_environment(manifest: dict, paths: dict[str, Path]) -> tuple[dict | None, dict | None]:
    """Verify launch JSONs against the files actually named by the benchmark manifest."""
    a_path, b_path = paths.get("a_launch"), paths.get("b_launch")
    if (a_path is None) != (b_path is None):
        raise ValueError("both launch JSON paths are required together")
    if a_path is None:
        return None, None
    environments = []
    for side, path in (("A", a_path), ("B", b_path)):
        expected = manifest.get(f"{side}_config_sha256")
        if not isinstance(expected, str) or file_hash(path).lower() != expected.lower():
            raise ValueError(f"{side} launch JSON SHA-256 differs from manifest")
        launch = read_json(path)
        env = launch.get("env", {})
        if not isinstance(env, dict):
            raise ValueError(f"{side} launch JSON env is not an object")
        environments.append(env)
    return environments[0], environments[1]


def env_label(environment: dict | None, name: str) -> str:
    if environment is None:
        return "실행 설정 파일 미제공"
    if name not in environment:
        return "미기록 (부모 환경 상속 가능)"
    value = environment[name]
    return "명시적으로 해제 (null)" if value is None else f"`{safe_text(value)}`"


def render(summary: dict, rows: list[dict], manifest: dict, a_build: dict, b_build: dict,
           paths: dict[str, Path]) -> str:
    collected = collect_pairs(rows, manifest)
    check_summary(summary, rows, collected)
    a_environment, b_environment = launch_environment(manifest, paths)
    config_check = manifest.get("inference_config_check") or {}
    config_hash = config_check.get("normalized_inference_config_sha256")
    same_config = isinstance(config_hash, str) and len(config_hash) == 64 and all(c in "0123456789abcdef" for c in config_hash.lower())
    if not same_config or not manifest.get("pack"):
        raise ValueError("manifest: shared pack and normalized inference-config check are required")
    a_exe = (config_check.get("A") or {}).get("exe")
    b_exe = (config_check.get("B") or {}).get("exe")
    if not a_exe or not b_exe or str(a_exe).casefold() == str(b_exe).casefold():
        raise ValueError("manifest: two distinct engine executables are required")
    environment = read_json(paths["environment"]) if "environment" in paths else None
    if environment is not None:
        for label, exe, key in (("Strata", a_exe, "strata_engine_sha256"),
                                ("Juud_engine", b_exe, "juud_engine_sha256")):
            recorded = environment.get(key)
            if not isinstance(recorded, str) or file_hash(Path(exe)).lower() != recorded.lower():
                raise ValueError(f"{label} executable SHA-256 differs from environment record")
    build_arch_same = a_build.get("archs") == b_build.get("archs") and a_build.get("archs") is not None
    source_a, source_b = manifest.get("A_source") or {}, manifest.get("B_source") or {}
    source_audit = None
    if source_b.get("source_correction"):
        if "source_capture" not in paths or "source_correction" not in paths:
            raise ValueError("corrected source provenance requires original manifest and correction audit")
        if environment is None:
            raise ValueError("corrected source provenance requires engine binary hashes")
        source_audit = read_json(paths["source_correction"])
        if (source_audit.get("original_manifest_sha256") != file_hash(paths["source_capture"]) or
                source_audit.get("corrected_manifest_sha256") != file_hash(paths["manifest"]) or
                source_audit.get("git_commit") != source_b.get("commit") or
                source_audit.get("engine_executable_sha256") != environment.get("juud_engine_sha256")):
            raise ValueError("source correction audit does not match current evidence")
    pack_name = str(manifest["pack"]).replace("\\", "/").rstrip("/").split("/")[-1]
    total_valid = sum(len(x["valid"]) for x in collected.values())
    expected_total = sum(x["attempted"] for x in collected.values())
    lines = ["# Strata와 Juud_engine: RTX 4090 비교 보고서", "",
             "A는 Strata, B는 Juud_engine입니다. 양수의 paired gain은 B가 빠르다는 뜻입니다.",
             f"벤치 시작(UTC): {safe_text(manifest.get('started_utc'))} · 유효 요청쌍: {total_valid}/{expected_total}", "",
             "## 비교 조건과 출처", "",
             "| 항목 | A: Strata | B: Juud_engine |", "| --- | --- | --- |",
             f"| 소스 커밋 | `{safe_text(source_a.get('commit'))}` | `{safe_text(source_b.get('commit'))}` |",
             f"| 작업 트리 변경 | {safe_text(source_a.get('dirty'))} | {safe_text(source_b.get('dirty'))} |",
             f"| BUILD source/version | {safe_text(a_build.get('source'))} / {safe_text(a_build.get('version'))} | {safe_text(b_build.get('source'))} / {safe_text(b_build.get('version'))} |",
             f"| BUILD 소스 지문 | `{safe_text(a_build.get('src'))}` | `{safe_text(b_build.get('src'))}` |",
             f"| CUDA 아키텍처 | {safe_text(a_build.get('archs'))} | {safe_text(b_build.get('archs'))} |",
             f"| BUILD.json SHA-256 | `{file_hash(paths['a_build'])}` | `{file_hash(paths['b_build'])}` |",
             "", f"- 공유 pack 디렉터리: `{safe_text(pack_name)}`"
             " (실제 경로는 manifest에 보존).",
             f"- 정규화 추론 설정 검증: 통과 (`{config_hash}`).",
             f"- 모델 확인 범위: 러너가 같은 pack·tokenizer 경로와 설정을 요구했습니다. " +
             ("원본 GGUF의 로컬 SHA-256은 아래 장비 기록에 별도로 보존했습니다." if
              environment is not None and environment.get("model_files") else
              "모델 파일별 SHA-256은 manifest에 없어 바이트 동일성은 별도로 입증해야 합니다."),
             f"- BUILD CUDA 아키텍처 일치: {'예' if build_arch_same else '확인 불가 또는 불일치'}. "
             "BUILD.json은 컴파일러 버전이나 실행 파일 해시를 보증하지 않습니다.",
             "", "## Juud_engine 최적화 설정", "",
             "아래 값은 manifest의 SHA-256과 일치하는 A/B 실행 설정 JSON의 `env` 항목입니다. "
             "실행 프로세스 내부에서 환경변수를 다시 읽어 검증한 기록은 아닙니다.", "",
             "| 환경변수 | A: Strata | B: Juud_engine |", "| --- | --- | --- |"]
    if environment is not None:
        hardware = environment.get("gpu") or {}
        evidence = ["", "## 장비와 바이너리 지문", "",
                    f"- GPU: {safe_text(hardware.get('name'))}, VRAM {safe_text(hardware.get('memory_total_mib'))} MiB, "
                    f"드라이버 {safe_text(hardware.get('driver_version'))}, compute {safe_text(hardware.get('compute_capability'))}.",
                    f"- CPU: {safe_text(environment.get('cpu'))}; 물리 RAM {safe_text(environment.get('physical_ram_bytes'))} bytes; "
                    f"OS {safe_text(environment.get('os_version'))}.",
                    f"- CUDA {safe_text(environment.get('cuda_toolkit'))}; MSVC {safe_text(environment.get('msvc_compiler'))}.",
                    f"- Strata 실행 파일 SHA-256: `{environment['strata_engine_sha256']}`.",
                    f"- Juud_engine 실행 파일 SHA-256: `{environment['juud_engine_sha256']}`."]
        if environment.get("model_repository") and environment.get("model_revision"):
            evidence.append(f"- IQ3_S 원본: `{safe_text(environment['model_repository'])}` "
                            f"revision `{safe_text(environment['model_revision'])}`.")
        if environment.get("mtp_repository") and environment.get("mtp_revision"):
            evidence.append(f"- MTP 원본: `{safe_text(environment['mtp_repository'])}` "
                            f"revision `{safe_text(environment['mtp_revision'])}`; "
                            f"31개 텐서 manifest SHA-256 `{safe_text(environment.get('mtp_manifest_sha256'))}`.")
        model_files = environment.get("model_files") or []
        if model_files:
            evidence += ["", "모델 GGUF 파일은 다운로드 완료 후 로컬 SHA-256으로 재확인했습니다.", "",
                         "| GGUF 조각 | 바이트 | SHA-256 |", "| --- | ---: | --- |"]
            for item in model_files:
                if item.get("verification") != "local_sha256" or not isinstance(item.get("sha256"), str):
                    raise ValueError("environment model file lacks local SHA-256 verification")
                evidence.append(f"| {safe_text(item.get('name'))} | {safe_text(item.get('bytes'))} | `{item['sha256']}` |")
        evidence += [""]
        position = lines.index("## Juud_engine 최적화 설정")
        lines[position:position] = evidence
    if source_audit is not None:
        position = lines.index("## Juud_engine 최적화 설정")
        lines[position:position] = ["Juud 소스 커밋은 측정 당시 러너의 Windows `safe.directory` 경로 오류로 비어 "
                                    "있었습니다. 원본 `manifest.capture.json`을 보존하고, 측정 직후 깨끗한 작업 트리와 "
                                    "동일 실행 파일 해시를 확인한 `source-correction.json`을 근거로 보완했습니다.", ""]
    for option in ("JUUD_POOL_ADAPTIVE_SPIN", "JUUD_SKIP_UNUSED_ACTQ", "STRATA_POOL_SPIN_US"):
        lines.append(f"| `{option}` | {env_label(a_environment, option)} | {env_label(b_environment, option)} |")
    lines += ["", "- `JUUD_POOL_ADAPTIVE_SPIN=1`: CPU 전문가 작업의 단계에 따라 워커 대기 시간을 조정합니다. "
              "명시적인 `STRATA_POOL_SPIN_US` 값이 있으면 고정 대기 정책이 우선합니다.",
              "- `JUUD_SKIP_UNUSED_ACTQ=1`: 단일 GPU 구성에서 CPU 전문가 작업이 없는 토큰의 CPU 활성값 양자화를 생략합니다. "
              "해당 작업이 실제로 발생했는지와 성능 효과는 이 설정값만으로 확인할 수 없습니다.",
              "- 두 옵션 모두 기본값은 비활성입니다. A/B 설정에서 항목이 빠지면 부모 프로세스 환경을 상속할 수 있어 "
              "실제 적용 여부를 단정할 수 없습니다.",
             "", "## 처리량과 지연", "",
             "아래 수치는 같은 요청 SHA-256의 유효 A/B 쌍만 사용한 중앙값입니다. 향상률은 각 쌍의 비율을 먼저 "
             "계산한 뒤 중앙값을 취했습니다. 모델 시작 시간은 제외했습니다.", "",
             "| 작업 | 유효쌍 | 입력 tok/s A → B (gain) | 출력 tok/s A → B (gain) | 첫 응답 초 A → B (gain) | 전체 초 A → B (gain) |",
             "| --- | ---: | --- | --- | --- | --- |"]
    all_valid = []
    for case, data in collected.items():
        valid = data["valid"]
        all_valid.extend(valid)
        m = metrics_for(valid)
        def cell(key: str) -> str:
            metric = m[key]
            return f"{fmt_value(metric['A'])} → {fmt_value(metric['B'])} ({fmt_gain(metric['gain'])})"
        lines.append(f"| {case} | {len(valid)}/{data['attempted']} | {cell(METRICS[0])} | {cell(METRICS[1])} | "
                     f"{cell(METRICS[2])} | {cell(METRICS[3])} |")
    lines += ["", "## 불완전 출력과 오류", "",
              f"- 전체 기대 요청쌍 {expected_total}개 중 {expected_total - total_valid}개를 수치 계산에서 제외했습니다."]
    for case, data in collected.items():
        if data["failures"]:
            reasons = "; ".join(f"{reason} {count}쌍" for reason, count in sorted(data["failures"].items()))
            lines.append(f"- {case}: {reasons}.")
    if total_valid == expected_total:
        lines.append("- 기록된 모든 요청쌍이 완료·토큰수·시간 검사와 각 출력의 무결성 해시 검사를 통과했습니다. A/B 출력의 상호 일치율은 아래 표에 따로 표시합니다.")
    lines += ["", "## MTP 수용과 출력 일치", "",
              "MTP 수용률은 유효 요청쌍에서 기록된 수용 토큰 수 / 제안 토큰 수입니다. 제안 수가 0이면 비율을 계산하지 않습니다.", "",
              "| 작업 | A 수용/제안 | B 수용/제안 | 출력 해시 일치 |",
              "| --- | ---: | ---: | ---: |"]
    for case, data in collected.items():
        valid = data["valid"]
        matches = sum(a.get("output_sha256") == b.get("output_sha256") for a, b, _, _ in valid)
        lines.append(f"| {case} | {mtp(valid, 0)} | {mtp(valid, 1)} | {matches}/{len(valid)} |")
    lines += ["", "[원본 Strata의 재현성 설명](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/DETAILS.md)에 따르면 "
              "greedy 출력도 IQ 전문가의 단일·다중 토큰 커널 반올림, draft window, 적응형 GPU 캐시와 PCIe 실행 위치에 따라 "
              "달라질 수 있습니다. 같은 요청과 출력 토큰 수라도 답변 및 MTP 수용률 차이는 처리 시간에 영향을 줄 수 "
              "있습니다. 해시 불일치만으로 기능 오류나 품질 차이를 단정할 수 없으며, 해시 일치는 품질 평가를 대신하지 "
              "않습니다.", "", "## GPU·CPU·VRAM 관측 범위", "",
              "아래 표는 러너가 요청 종료 후 `/metrics`에서 받은 **완료 무렵 단일 스냅샷**의 최소–최대입니다. "
              "요청 전체 평균, 요청 중 최고치, 소비 에너지 또는 프로세스별 CPU 사용률이 아닙니다.", "",
              "| 관측값 | A: Strata | B: Juud_engine |", "| --- | --- | --- |",
              f"| GPU 사용률 | {observed_range(all_valid, 0, 'gpu_util', unit='%')} | {observed_range(all_valid, 1, 'gpu_util', unit='%')} |",
              f"| 시스템 CPU 사용률 | {observed_range(all_valid, 0, 'cpu', unit='%')} | {observed_range(all_valid, 1, 'cpu', unit='%')} |",
              f"| VRAM 사용량 | {observed_range(all_valid, 0, 'gpu_mem_used', scale=2**30, unit=' GiB')} | {observed_range(all_valid, 1, 'gpu_mem_used', scale=2**30, unit=' GiB')} |",
              f"| GPU 전력 | {observed_range(all_valid, 0, 'gpu_power', unit=' W')} | {observed_range(all_valid, 1, 'gpu_power', unit=' W')} |",
              "", "## 판단과 한계", ""]
    sampling = manifest.get("gpu_sampling") or {}
    if sampling.get("enabled"):
        sampling_note = ("별도의 `nvidia-smi` 폴링 기록은 `runs.jsonl`의 `gpu_sampling.file`에서 찾을 수 있습니다. "
                         "요청별 `gpu_sampling.by_gpu`의 평균·최소·최대는 **폴링 명령 구간이 요청과 겹친 샘플**의 집계이며, "
                         "정확한 요청 구간 평균·최고치나 소비 에너지가 아닙니다. 위 표에는 이 폴링 집계를 섞지 않았습니다.")
        position = lines.index("## 판단과 한계")
        lines[position:position] = [sampling_note, ""]
    gpu_names = {str((row.get("server_hardware_static") or {}).get("gpu_name")) for pair in all_valid
                 for row in pair[:2] if (row.get("server_hardware_static") or {}).get("gpu_name")}
    cpu_names = {str((row.get("server_hardware_static") or {}).get("cpu_name")) for pair in all_valid
                 for row in pair[:2] if (row.get("server_hardware_static") or {}).get("cpu_name")}
    hardware_position = lines.index("## GPU·CPU·VRAM 관측 범위") + 2
    lines.insert(hardware_position,
                 f"기록된 장비명: GPU {safe_text(', '.join(sorted(gpu_names)) if gpu_names else None)}, "
                 f"CPU {safe_text(', '.join(sorted(cpu_names)) if cpu_names else None)}.")
    lines.insert(hardware_position + 1, "")
    gains = {case: metrics_for(data["valid"])["decode_tok_s"]["gain"] for case, data in collected.items()}
    known = [(case, value) for case, value in gains.items() if value is not None]
    if not known:
        lines.append("- 유효한 출력 속도 비교가 없어 성능 향상 여부를 판단할 수 없습니다.")
    elif all(value <= 0 for _, value in known):
        lines.append("- 측정된 모든 작업에서 Juud_engine의 출력 속도 향상이 확인되지 않았습니다. 음수 gain은 성능 악화입니다.")
    elif any(value <= 0 for _, value in known):
        lines.append("- 일부 작업에서 출력 속도가 개선됐지만 다른 작업은 같거나 악화됐습니다. 범용 속도 우위를 주장할 수 없습니다.")
    else:
        lines.append("- 측정된 작업의 쌍별 출력 속도 gain 중앙값이 모두 양수입니다. 이는 이 모델·PC·설정·입력에 한정된 결과입니다.")
    if any(len(data["valid"]) < 3 for data in collected.values()):
        lines.append("- 작업당 유효쌍이 3개 미만인 항목이 있어 그 수치는 탐색적으로만 해석해야 합니다.")
    if any((source_a.get("dirty"), source_b.get("dirty"))):
        lines.append("- 소스 작업 트리에 미커밋 변경이 기록됐습니다. 커밋 ID만으로 실제 바이너리를 재현할 수 없습니다.")
    if a_build.get("src") and a_build.get("src") == b_build.get("src"):
        lines.append("- 두 BUILD 소스 지문이 같습니다. Juud 변경이 실행 바이너리에 포함됐는지 다시 확인해야 합니다.")
    lines += ["- 이 러너는 합성 코드·한국어 입력과 단일 요청을 측정합니다. 품질, 장시간 안정성, 동시 요청 처리량, "
              "실사용 전체를 대표하지 않습니다.",
              ("- 온도·클록·전력 제한의 시간 이력은 제공된 GPU 폴링 파일에서 확인해야 합니다. "
               "모델 GGUF의 로컬 해시는 별도 환경 기록에 보존했습니다." if
               environment is not None and environment.get("model_files") else
               "- 온도·클록·전력 제한의 시간 이력과 모델 파일 해시를 추가로 보존해야 하드웨어 상태와 모델 동일성을 더 강하게 검증할 수 있습니다."),
              "", "## 원자료 무결성", "",
              "| 파일 | SHA-256 |", "| --- | --- |"]
    for name in ("summary", "runs", "manifest", "source_capture", "source_correction",
                 "environment", "a_build", "b_build", "a_launch", "b_launch"):
        if name not in paths:
            continue
        lines.append(f"| {paths[name].name} ({name}) | `{file_hash(paths[name])}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--strata-build", type=Path, required=True)
    parser.add_argument("--juud-build", type=Path, required=True)
    parser.add_argument("--strata-launch", type=Path, help="A launch JSON; requires --juud-launch and matching manifest SHA-256")
    parser.add_argument("--juud-launch", type=Path, help="B launch JSON; requires --strata-launch and matching manifest SHA-256")
    parser.add_argument("--environment", type=Path, help="measured host, locally verified model hashes and engine binary hashes")
    parser.add_argument("--source-capture", type=Path, help="unaltered benchmark manifest before an audited source correction")
    parser.add_argument("--source-correction", type=Path, help="audit record for a post-run source correction")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = {"summary": args.summary, "runs": args.runs, "manifest": args.manifest,
             "a_build": args.strata_build, "b_build": args.juud_build}
    if (args.strata_launch is None) != (args.juud_launch is None):
        parser.error("--strata-launch and --juud-launch must be provided together")
    if args.strata_launch is not None:
        paths["a_launch"], paths["b_launch"] = args.strata_launch, args.juud_launch
    if args.environment is not None:
        paths["environment"] = args.environment
    if (args.source_capture is None) != (args.source_correction is None):
        parser.error("--source-capture and --source-correction must be provided together")
    if args.source_capture is not None:
        paths["source_capture"], paths["source_correction"] = args.source_capture, args.source_correction
    summary, manifest = read_json(args.summary), read_json(args.manifest)
    a_build, b_build = read_json(args.strata_build), read_json(args.juud_build)
    rows = load_rows(args.runs)
    report = render(summary, rows, manifest, a_build, b_build, paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
