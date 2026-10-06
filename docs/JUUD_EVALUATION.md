# Juud_engine evaluation on an RTX 4090

**Status:** no local Strata-versus-Juud_engine model benchmark has been completed. Leave the result cells below empty
until they can be filled from a saved, valid run of [`bench/juud_compare.py`](../bench/README.md).

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

This is motivated by [Strata issue #921](https://github.com/Niko1221/Strata/issues/921), which reports lower CPU
contention in a GPU-heavy **dual** RTX 4090 configuration and also describes slower wake-ups for CPU-positive
layers. That report is a hypothesis for this **single** RTX 4090 experiment, not its result.

## Reproduction record

The benchmark guide gives the exact [launch JSON and command](../bench/README.md#run). Record this information
with the raw result directory before filling the comparison table:

| Item | Value |
| --- | --- |
| Strata source commit | [`6f32ec070f23ced9f50e704d854d775da52591ab`](https://github.com/Niko1221/Strata/tree/6f32ec070f23ced9f50e704d854d775da52591ab) |
| Juud_engine source commit | |
| CPU, GPU, RAM, OS | |
| NVIDIA driver, CUDA toolkit, compiler | |
| Exact IQ3_S model repository, revision, file hashes | |
| Engine config and launch JSON hashes | |
| Context, KV type, MTP, expert cache, PCIe share, worker count | |
| Run date, GPU clocks/power/temperature, other running workloads | |
| Raw results directory or release artifact | |

Use one shared model pack and identical request bytes for both arms. Build each engine from its pinned source with
the same compiler and CUDA options. The intended treatment is the pair of Juud environment settings above.
Run the paired harness with `STRATA_POOL_SPIN_US` unset and both Juud flags enabled only for the Juud arm. Preserve
failed or incomplete requests in the raw data.

## Results

Fill these cells only from the saved `summary.json`, with the corresponding `runs.jsonl`, request hashes, launch
configs, and server logs available for inspection. Report each workload separately; a positive paired gain means
Juud_engine is faster. A gain in one row does not establish a general speedup.

| Workload | Valid pairs | Strata prefill tok/s | Juud prefill tok/s | Strata decode tok/s | Juud decode tok/s | Paired decode gain | TTFT and total latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Code, 4K prompt | | | | | | | |
| Code, 32K prompt | | | | | | | |
| Code, 128K prompt | | | | | | | |
| Korean, 2K prompt | | | | | | | |

Before publishing a percentage claim, inspect valid-pair counts, output text, MTP draft acceptance, CPU work,
cache hit rates, and any regressions. Keep the conclusion limited to the measured model, hardware, settings, and
workloads. Publish a neutral or negative result when the experiment does not show an improvement.

## Source and model licenses

Juud_engine retains [Strata's MIT notice](../LICENSE) from the pinned upstream source. The full model weights and
IQ3_S pack are obtained separately. The inherited experimental projection vector in
`data/experimental-speed-projection` has Qwen's license. The official base model has the
[Qwen Community License 1.0](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/LICENSE); its terms include
a separate license for certain commercial Model-as-a-Service and AI work assistant businesses, with an internal-use
exception. Check the terms of the exact quantized model files as well.
