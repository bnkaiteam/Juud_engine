# Juud_engine international launch copy

These ready-to-edit messages describe the [published RTX 4090 comparison](../bench/results/2026-10-06-rtx4090-iq3_s/README.md).
Keep the workload, GPU, model and Strata version in the claim. Link readers to the method and paired data.

## One sentence

> Juud_engine is an experimental Strata v0.1.39 fork for local Qwen3.8-Flash-Next; on one RTX 4090, a separate
> three-pair-per-workload control with identical A/B outputs measured 9.6–15.6% higher decode throughput.

## GitHub, Reddit or forum post

**Suggested title:** I tested a Strata fork on one RTX 4090: higher Qwen3.8-Flash-Next decode throughput, with
paired measurements

> I built Juud_engine, an experimental fork of Strata v0.1.39 with two opt-in CPU-side changes: shorter worker
> spinning after completed expert batches, and skipped CPU activation quantization for GPU-only tokens in mixed
> multi-token batches. I compared it with the pinned Strata executable on one RTX 4090 using the same
> Qwen3.8-Flash-Next IQ3_S pack. Five pairs per workload under normal adaptive settings measured median paired
> decode-throughput gains of 3.1–9.1% across four prompts. Most normal-run A/B answers differed, so that result
> does not isolate the code's effect. In a separate three-pair-per-workload control, all 12 A/B outputs matched
> byte for byte and decode-throughput gains were 9.6–15.6%. The control uses different cache and PCIe settings.
> Normal-run full-response latency improved by 0.5–5.6%; the larger decode gain is not an end-to-end speed claim.
> I published the paired metrics, hashes, code changes and method. You need to build this fork and use `RUN-JUUD`
> to run the measured optimizations. I'd welcome independent replications, especially on other GPUs and with
> concurrent requests: https://github.com/bnkaiteam/Juud_engine

## Short social post

> Juud_engine: an experimental Strata v0.1.39 fork for local Qwen3.8-Flash-Next. One RTX 4090 + IQ3_S:
> +3.1–9.1% median paired decode throughput in normal runs; +9.6–15.6% in a separate 12/12 same-output control.
> Two opt-in CPU changes, published paired data. Build from source and enable with `RUN-JUUD`.
> https://github.com/bnkaiteam/Juud_engine

## Answer the likely questions

**Is the whole request 15% faster?** No. The 9.6–15.6% figure is answer-generation throughput in a separate
reproducibility control. In normal runs, paired full-response latency improved by 0.5–5.6% across the four tests.

**Will a default Strata installer or prebuilt give these results?** No. Build Juud_engine from its source and use
`RUN-JUUD`; the wrapper checks the selected engine path and local build record, then enables both flags. The inherited default setup can install
an original Strata prebuilt.

**Does it produce the same answers?** In the controlled comparison, 12/12 paired outputs matched byte for byte.
In the normal adaptive comparison, 5/20 did. That difference alone does not establish a quality change.

**Is it faster on H100, AMD or with many users?** Those scenarios have not been benchmarked. The H100 document
is a capacity assessment only.

Avoid calling it the “fastest Strata-compatible engine,” a “drop-in speedup,” “15% faster answers,” or an
energy-saving or quality improvement until those claims have matching evidence.
