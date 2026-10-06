# Juud_engine evaluation on an RTX 4090

**Status (2026-10-06):** a five-pair main comparison and a separate three-pair output-reproducibility control
completed on one RTX 4090. All 32 A/B pairs passed the runner's validity checks. See the
[published reports and privacy-reduced paired metrics](../bench/results/2026-10-06-rtx4090-iq3_s/README.md) and the
[runner's method](../bench/README.md).

## Change being evaluated

The original Strata expert-pool workers spin for up to 20 ms before sleeping. This fork adds an opt-in
`JUUD_POOL_ADAPTIVE_SPIN=1` policy: after a completed CPU expert batch, workers use a 100 µs spin; between the
gate/up and down phases of the same batch, they keep Strata's 20 ms window. An explicit `STRATA_POOL_SPIN_US`
still selects a fixed spin and disables the adaptive policy. The default is the original Strata behavior.

The second opt-in change, `JUUD_SKIP_UNUSED_ACTQ=1`, applies to the single-GPU expert dispatch path. When a token's
selected experts are all GPU-owned, Juud skips CPU activation quantization for that token. The CPU quantized
activation is consumed only by CPU expert jobs, so that token has no consumer for it. The default keeps Strata's
original calculation. The measured comparison enables both changes together; it cannot assign any gain to one
change without a separate ablation run.

This was motivated by [Strata issue #921](https://github.com/Niko1221/Strata/issues/921), which reports lower CPU
contention in a GPU-heavy **dual** RTX 4090 configuration and also describes slower wake-ups for CPU-positive
layers. That report concerned different hardware and should not be substituted for this single-RTX-4090 result.

## Reproduction record

The [benchmark guide](../bench/README.md#run) gives the runner command. The published
[result directory](../bench/results/2026-10-06-rtx4090-iq3_s/README.md) contains detailed reports, paired
measurements, request and output hashes, `summary.json`, public manifests, and provenance hashes. The complete
local capture, including launch JSON, requests, generated text, server logs and GPU samples, is preserved in a
local ZIP because it contains PC paths and full output text. Model weights and generated pack data are not
redistributed.

| Item | Value |
| --- | --- |
| Strata source commit | [`6f32ec070f23ced9f50e704d854d775da52591ab`](https://github.com/Niko1221/Strata/tree/6f32ec070f23ced9f50e704d854d775da52591ab) |
| Juud_engine source commit at main run | `cd565c7a22e604899f834a6a2c19ed0fcc659771`; [source-correction audit](../bench/results/2026-10-06-rtx4090-iq3_s/primary/source-correction.json) records how this was verified after a manifest capture error |
| Juud_engine source commit at control run | `312daafe01cf464f9bca1c52b34b161d3b7b3be2`; benchmark provenance code changed, compiled engine binary was unchanged |
| CPU, GPU, RAM, OS | i7-13700, RTX 4090 (24,564 MiB), 137,167,679,488 bytes physical RAM, Windows NT 10.0.22621.0 |
| NVIDIA driver, CUDA toolkit, compiler | 591.86, CUDA 13.0 V13.0.88, MSVC 19.44.35220 x64 |
| Exact IQ3_S model repository and revision | `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF`, `ed59f92082b1e93c0e96d60a8b11aab089b52f09`; both locally verified GGUF SHA-256 values are in [benchmark_environment.json](../bench/results/2026-10-06-rtx4090-iq3_s/benchmark_environment.json) |
| Compiled engine binary SHA-256 | Strata `c12f2928ab95c5defc54a5cf9e3c4d9f1f2442dd60a0bc97e44a41c1fe1cd395`; Juud `e797b44993cbcff23d5cd686941c1f4a1b381545ea002bbb4f8d0a9940d5ed87` |
| Engine config and launch JSON hashes | In the corresponding `manifest-public.json` and `public-provenance.json`; inference configurations were normalized and checked for equality within each A/B experiment |
| Common model settings | 131,072 maximum context, int8 KV, 32,768 resident KV, MTP with `--spec 4 --spec-min-p 0.5`, automatic expert cache and prefill |
| Date and GPU telemetry | 2026-10-06 UTC; locally preserved per-request `nvidia-smi` samples record clocks, power, temperature, usage, and VRAM. They do not establish process-specific energy. |
| Public results | [Main, five pairs per workload](../bench/results/2026-10-06-rtx4090-iq3_s/primary/summary.json); [control, three pairs per workload](../bench/results/2026-10-06-rtx4090-iq3_s/control/summary.json) |

Both arms used one shared model pack and identical request bytes, with one server running at a time. Each server
received a warm-up. Pair order alternated A/B and B/A. The treatment was both Juud environment flags enabled in
B only; `STRATA_POOL_SPIN_US` was explicitly unset in both arms. The engine binaries were built with the same
MSVC and CUDA toolkit, targeting compute 8.9. The runner preserves failed or incomplete requests in raw data;
none of the measured pairs was excluded.

## Main result: normal adaptive settings

These numbers come from the saved [main `summary.json`](../bench/results/2026-10-06-rtx4090-iq3_s/primary/summary.json).
The per-arm speeds and times are medians; each percentage is the **median of the five paired gains**, so a gain
need not equal the ratio of the two displayed medians. A positive gain means Juud_engine was faster. Startup was
excluded. All runs generated 256 output tokens.

| Workload | Valid pairs | Prefill tok/s Strata → Juud | Decode tok/s Strata → Juud | Paired decode gain | Paired total-latency improvement | Identical A/B output hashes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Code, 4K prompt | 5/5 | 2,189.67 → 2,191.55 | 76.14 → 80.25 | +9.1% | +5.6% | 4/5 |
| Code, 32K prompt | 5/5 | 4,344.22 → 4,378.11 | 99.32 → 100.31 | +3.6% | +1.4% | 1/5 |
| Code, 128K prompt | 5/5 | 4,134.57 → 4,131.11 | 97.28 → 100.76 | +3.1% | +0.5% | 0/5 |
| Korean, 2K prompt | 5/5 | 1,178.57 → 1,182.24 | 77.63 → 83.42 | +7.5% | +4.3% | 0/5 |

The full report also gives TTFT, per-pair distributions, MTP draft acceptance, CPU and GPU observations, and
source and file hashes. The primary run's `B_source` entry was missing due to a Windows `safe.directory` path
capture bug. The original manifest remains in the local ZIP; the published redacted `source-correction.json`
documents the immediate clean-tree and unchanged-binary verification used to correct it.

**Output limitation:** the main run's A/B output text differs in most pairs. Upstream Strata
[documents non-determinism in greedy output](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/DETAILS.md)
from CPU expert rounding, draft windows, adaptive cache, and PCIe execution placement. Different generated
tokens and MTP acceptance may affect speed. The main-run gain therefore cannot be attributed solely to either
or both code changes, and output-hash differences alone do not establish a quality regression.

## Separate control: matched output text

For this control only, **both** arms set `STRATA_IQ_MT_MIN=1` and engine options `--prompt-cache 0`,
`--adapt-swaps 0`, and `--pcie-frac 0` following upstream's reproducibility guidance. These settings change the
execution profile, including CPU expert work. This is a distinct three-pair experiment with its own
[control `summary.json`](../bench/results/2026-10-06-rtx4090-iq3_s/control/summary.json); its speeds should not
be pooled with or directly compared against the normal adaptive settings above.

| Workload | Valid pairs | Decode tok/s Strata → Juud | Paired decode gain | Paired total-latency improvement | Identical A/B output hashes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Code, 4K prompt | 3/3 | 69.45 → 79.61 | +14.7% | +8.4% | 3/3 |
| Code, 32K prompt | 3/3 | 69.89 → 77.59 | +9.6% | +2.5% | 3/3 |
| Code, 128K prompt | 3/3 | 68.45 → 72.46 | +15.6% | +1.2% | 3/3 |
| Korean, 2K prompt | 3/3 | 49.34 → 56.41 | +14.2% | +9.2% | 3/3 |

Matching text removes one major confounder, but these small single-request samples do not isolate each option or
prove a general speedup. Neither run measures response quality, concurrency, long-term stability, or H100 speed.
The [H100 guide](H100_SINGLE_GPU.md) is a capacity and build assessment, not an H100 benchmark.

## Source and model licenses

Juud_engine retains [Strata's MIT notice](../LICENSE) from the pinned upstream source. The full model weights and
IQ3_S pack are obtained separately. The inherited experimental projection vector in
`data/experimental-speed-projection` has Qwen's license. The official base model has the
[Qwen Community License 1.0](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/LICENSE); its terms include
a separate license for certain commercial Model-as-a-Service and AI work assistant businesses, with an internal-use
exception. Check the terms of the exact quantized model files as well.
