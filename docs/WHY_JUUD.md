# Why try Juud_engine?

Juud_engine is an experimental fork of **Strata v0.1.39 (`6f32ec0`)** for local
Qwen3.8-Flash-Next. Its case for trying it is specific: **higher measured decode throughput on one RTX 4090
with the IQ3_S pack**, using two opt-in changes to CPU work during inference. The comparison is against the
pinned Strata build, with the same prompts and model pack, rather than against every version or configuration
of Strata.

| Difference | What Juud changes | Why it could help |
| --- | --- | --- |
| CPU worker wait | After a completed expert batch, reduce busy spinning from 20 ms to 100 µs; keep the original 20 ms window between the two phases of an active batch. An explicit `STRATA_POOL_SPIN_US` retains its fixed policy. | Less avoidable worker spinning between batches while preserving prompt wake-ups within a batch. |
| Activation quantization | In a single-GPU, mixed multi-token batch, skip CPU activation quantization for a token whose selected experts are all GPU-owned; other tokens may still need CPU experts. | The skipped CPU activation has no CPU job that can consume it. A wholly GPU-owned batch already skips this calculation in Strata. |
| Use of the measured engine | `RUN-JUUD.bat`/`RUN-JUUD.sh` checks the selected engine path and build metadata, then enforces both options after saved config values are applied. | Rejects installs recorded as Strata prebuilts and configs that point to another engine. The metadata check is not binary attestation. |

The first two mechanisms are code-level differences, **not separately measured improvements**. Both were
enabled in every Juud benchmark arm. The run wrapper is an onboarding guard, not an inference speed change.

## What the RTX 4090 comparison found

The [benchmark record](../bench/results/2026-10-06-rtx4090-iq3_s/README.md) has the method, paired data and
SHA-256 provenance. Each workload requested 256 generated tokens with no prompt-prefix reuse. Positive values
below are median paired gains over the pinned Strata executable.

| Prompt | Normal decode tok/s gain, 5 pairs | Normal total-latency gain | Same-output control decode tok/s gain, 3 pairs |
| --- | ---: | ---: | ---: |
| Code, 4K | +9.1% | +5.6% | +14.7% |
| Code, 32K | +3.6% | +1.4% | +9.6% |
| Code, 128K | +3.1% | +0.5% | +15.6% |
| Korean, 2K | +7.5% | +4.3% | +14.2% |

Normal A/B output text matched in 5/20 pairs. Strata's adaptive GPU expert cache, CPU rounding, PCIe placement
and speculative draft windows can change greedy output; different continuations can change timing. The
**separate** control disabled prompt caching, adaptive swaps and PCIe expert work and set `STRATA_IQ_MT_MIN=1` in
both arms. Its 12/12 A/B outputs matched byte for byte. These settings alter the execution profile, so its gains
cannot be combined with the normal-run gains. Faster decoding also does not mean the entire answer appears that
much sooner: with a 128K input, the normal run's median paired total-latency gain was only +0.5%.

## What to expect when switching

- **You must build this source.** The inherited default setup can fetch a Strata prebuilt that contains none of
  Juud's changes. Follow the [README quick start](../README.md#run-the-tested-juud-path), then use `RUN-JUUD`.
- **The model is separate.** Download and licensing terms for the model or a quantization are not covered by the
  engine's MIT license. The official Qwen3.8-Flash-Next license has conditions for some commercial services.
- **Strata remains the foundation.** Juud keeps its local server and uses Strata's GPU, CPU and storage layout.
  The speed claim is limited to the tested fork, model, hardware and requests.

We have **not** shown better model quality, prefill throughput, first-token latency, energy use, H100 speed,
multi-user throughput or long-run reliability. We have not compared against a manually tuned
`STRATA_POOL_SPIN_US` policy or isolated the two Juud changes in an ablation. Independent replications on other
systems are welcome. The [H100 guide](H100_SINGLE_GPU.md) assesses memory fit and build steps; it is not a speed
benchmark.
