# Juud_engine

**Measured faster decoding for local Qwen3.8-Flash-Next on one RTX 4090.**

[한국어](README.ko.md) · [Why Juud?](docs/WHY_JUUD.md) · [RTX 4090 results and paired metrics](bench/results/2026-10-06-rtx4090-iq3_s/README.md)

Juud_engine is an experimental fork of [Strata](https://github.com/Niko1221/Strata) v0.1.39. It keeps Strata's
local inference server and adds two **opt-in** engine changes aimed at CPU work during decoding. On a single RTX 4090
with Qwen3.8-Flash-Next IQ3_S, median paired **decode throughput** improved in all four tested workloads against
the pinned [Strata `6f32ec0`](https://github.com/Niko1221/Strata/tree/6f32ec070f23ced9f50e704d854d775da52591ab).

## Why try Juud_engine?

1. **Measured decode gains on the tested PC.** The normal adaptive run measured +3.1% to +9.1% median paired
   decode throughput across four prompts, with five pairs per prompt. A separate three-pair control with identical
   A/B output text measured +9.6% to +15.6% under different reproducibility settings.
2. **Less avoidable CPU work by design.** Workers shorten their spin after a completed CPU expert batch, while
   retaining Strata's longer window between phases of that batch. On a single GPU, mixed multi-token batches can
   skip CPU activation quantization for tokens whose selected experts all run on the GPU.
3. **A checkable comparison.** The repository includes source changes, pair-level measurements, request/output
   hashes, model and binary hashes, methodology, and a [verification script](bench/verify_public_metrics.py).

Both changes are off by default. **Build this checkout and use `RUN-JUUD` to enable the measured path.** A normal
Strata prebuilt from the default setup flow does not include Juud's source changes.

## Measured against Strata v0.1.39

Each request generated 256 tokens with the same IQ3_S pack on the same RTX 4090 PC. These percentages are medians
of matched A/B ratios; positive values favor Juud_engine. Model startup is excluded.

| Prompt | Normal decode gain, 5 pairs | Normal full-response latency gain | Identical-output control decode gain, 3 pairs |
| --- | ---: | ---: | ---: |
| Code, 4K tokens | +9.1% | +5.6% | +14.7% |
| Code, 32K tokens | +3.6% | +1.4% | +9.6% |
| Code, 128K tokens | +3.1% | +0.5% | +15.6% |
| Korean, 2K tokens | +7.5% | +4.3% | +14.2% |

In the normal run, A/B output text matched in only **5/20 pairs**. Different continuations and MTP draft acceptance
can affect timing, so these numbers do not isolate the code changes. The separate control used Strata's
reproducibility settings in **both** arms and matched output text in **12/12 pairs**. Its cache and PCIe settings
differ from the normal run; do not pool the results. The two Juud changes were enabled together, without an
individual ablation. See the [full method, latencies, limitations, and public paired metrics](bench/results/2026-10-06-rtx4090-iq3_s/README.md).

## Run the tested Juud path

For NVIDIA CUDA 13 on Windows, first build the engine from this source and choose the Qwen3.8-Flash-Next **IQ3_S**
model size in setup to match the comparison above. Setup may need build tools and a large separate model download.
When reconfiguring an existing install, select the intended model, size and settings. Re-run the setup command after
a source update or when converting an existing Strata install; `--build` alone on an ordinary start of an installed
model does **not** rebuild.

```powershell
git clone https://github.com/bnkaiteam/Juud_engine.git
cd Juud_engine
.\START-HERE.bat --setup --build --no-start --family qwen --model IQ3_S
.\RUN-JUUD.bat
```

On Linux with an NVIDIA CUDA 13 local build toolchain:

```sh
git clone https://github.com/bnkaiteam/Juud_engine.git
cd Juud_engine
./setup.sh --setup --build --no-start --family qwen --model IQ3_S
./RUN-JUUD.sh
```

`RUN-JUUD` checks the selected model's engine path and the `BUILD.json` record for a local build and source
fingerprint matching this checkout. It clears any fixed `STRATA_POOL_SPIN_US` override, then enforces
`JUUD_POOL_ADAPTIVE_SPIN=1` and `JUUD_SKIP_UNUSED_ACTQ=1`, even if a saved model config has conflicting values.
It rejects installs recorded as Strata prebuilts; the build record is not a cryptographic attestation of the binary.
You can pass ordinary setup/start arguments to the wrapper. The engine still exposes Strata's OpenAI-compatible local API. See the [benchmark guide](bench/README.md)
to reproduce the comparison and [evaluation record](docs/JUUD_EVALUATION.md) for detailed provenance.

## Scope and provenance

This is a single-GPU, single-request RTX 4090 result. It does not establish a speed, quality, power, concurrent
throughput, or reliability advantage on other systems. The observed prefill and time-to-first-token changes were
small. A [single-H100 capacity and build guide](docs/H100_SINGLE_GPU.md) is available; H100 speed is unmeasured.
The full raw capture, which includes PC paths and complete generated text, is kept locally; GitHub contains
privacy-reduced paired metrics and original file hashes.

Juud_engine retains [Strata's MIT license](LICENSE). Model weights are not in this repository. The official
[Qwen3.8-Flash-Next model](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) uses the Qwen Community License 1.0;
check the terms of the exact model and quantization before providing a service. Other inherited third-party
notices remain in the source. The [preserved Strata README](UPSTREAM_README.md) contains upstream documentation,
download links, and benchmark figures; those figures are not Juud_engine measurements.
