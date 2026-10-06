# One H100 with 94 GB: Qwen3.8-Flash-Next

This guide applies to Juud_engine's fork of **Strata v0.1.39 at
[`6f32ec070f23ced9f50e704d854d775da52591ab`](https://github.com/Niko1221/Strata/tree/6f32ec070f23ced9f50e704d854d775da52591ab)**.
The links to Strata below use that commit, not the changing `main` branch. An H100 run of this fork has **not been
measured or validated**; the fit guidance below follows the published model sizes and the engine's memory layout.

## What fits

NVIDIA lists 94 GB H100 variants and compute capability 9.0 ([H100 NVL memory specification](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/h100/PB-11773-001_v01.pdf),
[supported GPU table](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/supported-gpus.html)). Qwen lists a
262,144-token native context for [Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next). Its unquantized
weights are much larger than 94 GB, so use one of the quantized packs supported by Strata:

| Original-model pack | Active shard, RAM + VRAM | Experts normally held in host RAM |
| --- | ---: | ---: |
| Q2_0 | 37.6 GB | 34 GB |
| IQ2_XS | 39.2 GB | 35.5 GB |
| IQ3_XXS | 47.0 GB | 43 GB |
| IQ3_S | 54.8 GB | 50 GB |

These are [Strata's published requirements](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/MODELS.md#the-sizes),
**not** total VRAM allocation or an H100 measurement. All four are plausible on one 94 GB card with enough system
memory. For a host with **96 GB RAM or more**, start with IQ3_S if quality is the priority; Strata recommends this size
at that RAM level. A 64 GB host can run IQ3_S but leaves little RAM for other work, especially at long context. The
installer's low-RAM mode can map experts from files and keep only the experts absent from the GPU in RAM; verify its
chosen mode and memory use on the actual host.

Strata also offers [Unsloth UD-IQ4_XS](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/MODELS.md#unsloth-ud-iq4_xs)
as a larger quantization: its **94 GB figure is a download size**, with 59.5 GB of experts. It needs at least 48 GB
host RAM; Strata says roughly 80 GB RAM keeps its experts off the SSD. Treat its H100 fit as unverified until startup
and a long request succeed. The still larger UD-Q4_K_XL is experimental and relies on an NVMe/host-RAM expert budget;
do not infer that a 94 GB H100 can keep its entire runtime in VRAM from the quantization name or download size.

## Where the data lives

In the standard layout, dense weights, the MTP draft runtime, active KV data and a cache of hot experts use VRAM.
The full expert set is also held in host RAM; the GPU expert cache consumes the free VRAM after other allocations, so
its actual slot count must be read from the startup log. At contexts of 64K or more, setup can stream most KV data
from host RAM. The separate **about 29 GB n-gram lookup shard stays on SSD**. Keep the model files, pack and MTP files
on an SSD with adequate free space; NVMe matters when low-RAM or Unsloth modes read experts from disk. This remains
a GPU + RAM + SSD engine even if a large expert cache fits on the H100
([Strata memory layout](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/DETAILS.md#how-it-works),
[model storage](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/MODELS.md#will-it-fit)).

## Build and validate

Build the engine **from this Juud_engine checkout** for H100's `sm_90` architecture. For CMake, set
`-DCMAKE_CUDA_ARCHITECTURES=90`; for the repository's Dockerfile, use
`docker build -t juud-h100 --build-arg CUDA_ARCHITECTURES=90 .`. The Docker default architectures omit `90`, and
the [pinned install guide](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/INSTALL.md#docker-linux)
requires a rebuild for an omitted card. Its CUDA 13 Docker image requires an NVIDIA driver of at least 580. Confirm
that the resulting binary is the **locally built Juud_engine** binary before testing its opt-in changes.

1. Install one original-model pack with `--family qwen --model IQ3_S --context 131072` (or choose IQ2_XS if host RAM is
   constrained). Start it and check the startup log for the detected GPU, successful model/MTP load, expert-cache
   slots, and free VRAM. Run a request that actually approaches the 128K limit.
2. Reconfigure with `START-HERE.bat --setup --context 262144` on Windows or
   `./setup.sh --setup --context 262144` on Linux. Check RAM and VRAM use during a request that approaches the full native
   context, plus correct completion and output. For IQ3_XXS and IQ3_S, Strata has **no published 262K measurement** and
   recommends 128K on a 64 GB RAM host by its estimate
   ([pinned context notes](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/DETAILS.md#speed-measured)).

No H100 throughput, latency or Juud_engine-versus-Strata speedup is implied by this guide. Record exact GPU variant,
host RAM, SSD, quantization, context, KV mode, engine commit and runtime logs before making such a claim.
