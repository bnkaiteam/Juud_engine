# Juud_engine international launch copy

These ready-to-edit messages describe the [published RTX 4090 comparison](../bench/results/2026-10-06-rtx4090-iq3_s/README.md)
of two **v0.1.39-based binaries**. The current Juud_engine source incorporates Strata v0.1.44.1, but that port
has no published paired benchmark. Keep the tested date, workload, GPU, model and both source versions in any
claim. Link readers to the method and paired data; do not imply the historical gains apply to a current build.
The [ablation runner](../bench/README.md#isolate-the-two-juud-switches) can measure each option separately;
no individual-option result has been published.

## One sentence

> An earlier v0.1.39-based Juud_engine build measured 9.6–15.6% higher decode throughput than pinned Strata
> v0.1.39 in a same-output RTX 4090 control; the current v0.1.44.1-based port has not been benchmarked.
> This does not establish an advantage over the current Strata release.

## GitHub or forums that allow AI-assisted drafts

Check each community's rules before posting. Hacker News and some Reddit project threads restrict
AI-written posts, so the project maintainer should write and submit those announcements personally.

**Suggested title:** Historical RTX 4090 comparison of a Juud_engine v0.1.39 fork and Strata v0.1.39

> On 6 October 2026 I tested an earlier Juud_engine build based on Strata v0.1.39 with two opt-in CPU-side
> changes: shorter worker spinning after completed expert batches, and skipped CPU activation quantization for GPU-only tokens in mixed
> multi-token batches. I compared it with the pinned Strata executable on one RTX 4090 using the same
> Qwen3.8-Flash-Next IQ3_S pack. Five pairs per workload under normal adaptive settings measured median paired
> decode-throughput gains of 3.1–9.1% across four prompts. Most normal-run A/B answers differed, so that result
> does not isolate the code's effect. In a separate three-pair-per-workload control, all 12 A/B outputs matched
> byte for byte and decode-throughput gains were 9.6–15.6%. The control uses different cache and PCIe settings.
> Normal-run full-response latency improved by 0.5–5.6%; the larger decode gain is not an end-to-end speed claim.
> I published the paired metrics, hashes, code changes and method. The current Juud_engine source incorporates
> Strata v0.1.44.1 and ports both changes, but I have not rerun this comparison on it. Build the current fork and
> use `RUN-JUUD` to enable its opt-in controls; the historical percentages do not predict its performance.
> I'd welcome independent replications, especially on other GPUs and with
> concurrent requests: https://github.com/bnkaiteam/Juud_engine

## Short social post

> Historical Juud_engine v0.1.39-based build vs Strata v0.1.39, one RTX 4090 + IQ3_S:
> +3.1–9.1% median paired decode throughput in normal runs; +9.6–15.6% in a separate 12/12 same-output control.
> Two opt-in CPU changes, published paired data. The current v0.1.44.1-based port has not been benchmarked.
> https://github.com/bnkaiteam/Juud_engine

## Answer the likely questions

**Is the whole request 15% faster?** No. The 9.6–15.6% figure is historical answer-generation throughput in a
separate reproducibility control. In those v0.1.39 runs, paired full-response latency improved by 0.5–5.6%
across the four tests. Neither figure has been measured on the current port.

**Will a default Strata installer or prebuilt give these results?** No. These numbers belong to the historical
Juud and Strata binaries. Build Juud_engine from source and use `RUN-JUUD` to run the current opt-in controls;
the current build needs a fresh benchmark. The wrapper checks the selected engine path and local build record,
then enables both flags. The inherited default setup can install an original Strata prebuilt.

**Does it produce the same answers?** In the historical controlled comparison, 12/12 paired outputs matched byte
for byte. In the normal adaptive comparison, 5/20 did. The current port has not had this check. The historical
difference alone does not establish a quality change.

**Is it faster on H100, AMD or with many users?** Those scenarios have not been benchmarked. The H100 document
is a capacity assessment only.

Avoid calling it the “fastest Strata-compatible engine,” a “drop-in speedup,” “15% faster answers,” faster than
current Strata, or an energy-saving or quality improvement until those claims have matching evidence.
