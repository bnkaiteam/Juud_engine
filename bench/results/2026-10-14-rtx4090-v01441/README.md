# RTX 4090: Strata v0.1.44.1 versus Juud opt-in controls

Measured 2026-10-14 on one Windows PC. This is an exploratory same-PC comparison, **not a verified speedup claim**: many A/B requests generated different text, so they took different decode paths. No model startup time is included in request latency. The raw prompts, outputs, and local paths are retained privately.

## Builds and hardware

| Arm | Source revision | `strata.exe` SHA-256 | `strata_kq.dll` SHA-256 |
| --- | --- | --- | --- |
| A: stock Strata v0.1.44.1 | `296b59d2f73c8f04a805df29c2fa97655adace78` | `735abe7b0a32bbf656fecf1e83eac75c629af34106bb275190388848c668ace0` | `480441f96f578f23a965147cfab6780d21cd4fb6f927871ab07b6eff0bb6cb4a` |
| B: Juud 11 on v0.1.44.1 | `e45f88311b169f8e8c451e727194a0dced680ccf` | `0364b5bb7a4dc621a691572aa47740c4b37ab3642f436bab5621551cbd8d861c` | `9ae1bf19e8beaaffe8f91d5174914b07f476acc342b645c3b833439d768359b7` |

The PC has one NVIDIA GeForce RTX 4090 (24,564 MiB reported VRAM), an Intel Core i7-13700, Windows 10.0.22621, and NVIDIA driver 591.86. A was built from a clean detached stock checkout with CUDA Toolkit 13.0.88, Visual Studio 2022/MSVC 19.44.35220, Release, `CMAKE_CUDA_ARCHITECTURES=89`, `STRATA_ENABLE_CUDA=ON`, and `STRATA_BUILD_TESTS=OFF`. The build used the pinned llama.cpp commit `3cf03257f219afbe7334045ff7c6a06ac68c627d`. B's existing build cache records the same Visual Studio generator, CUDA target and release flags. B's executable was built shortly before its source commit; its hash is fixed above, but the executable itself has no embedded commit attestation.

The tested B source revision was local and was not itself pushed. The merged release Git tree object `24d9e3281824a4e97b836c0c91ef60ba947d3778` has byte-identical engine source in `CMakeLists.txt`, `cmake/`, `src/`, `include/`, and `third_party/ggml/` relative to tested B; the tree also contains other release files.

Both arms used one shared Qwen3.8-Flash-Next GSQ-RCO IQ3_S pack, tokenizer, expert profile and MTP `rt` directory. Earlier local SHA-256 verification of its two GGUF shards recorded `4c1eb2ceb4915e1192f4f386021897bde56a97f40a0bb78bb86465e0f7d2aca3` (shard 1) and `316b46f3a2dbd68c900f43136ab9449f9dcc3725dfd8c794847c204bc161e113` (shard 2). The shared expert profile's SHA-256 is `8f59b4aa8873209dff11c11e37bcda9529a1335b724a1afeea37bf6388975baf`.

## Same settings and workload

Both arms ran `--expert-profile` with that same file, `--expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --max-context 131072 --kv int8 --kv-resident 32768`, plus the same pack, GGUF shards, tokenizer and MTP path. Vision and speed projection were off. B alone set `JUUD_POOL_ADAPTIVE_SPIN=1` and `JUUD_SKIP_UNUSED_ACTQ=1`; both arms cleared `STRATA_POOL_SPIN_US` and `JUUD_REQUIRE_SOURCE_BUILD`. The *controlled* series additionally set `--prompt-cache 0 --adapt-swaps 0 --pcie-frac 0` and `STRATA_IQ_MT_MIN=1` in both arms; these settings change the performance profile and should be read as a separate experiment.

Each request used temperature 0, `reasoning_effort=none`, streaming usage, and a 256-token output cap. The harness generated unique synthetic code prompts targeting 4,096 tokens and Korean prompts targeting 2,048 tokens. It checked actual prompt counts, full output, engine timing, usage counts, and no prefix reuse. It ran one warm-up per engine launch, then serial A/B launches in alternating order: A→B, B→A, and so on. A and B received identical request bytes within each pair. Compiler workers and the GPU were idle at preflight; GPU clocks sampled during requests were about 2,790–2,805 MHz. A prior 512-token smoke overlapped build activity and is excluded.

## Observations

Here B/A decode rate above 1 means B reported more generated tokens per second. A/B client time above 1 means B's request completed sooner. Ratios are geometric means of within-pair ratios; all successful requests generated 256 tokens.

| Series | Prompt | Valid pairs | Exact same output | Decode B/A geometric mean | Per-pair decode B/A | Client time A/B geometric mean |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| Main | Code 4K | 5/5 | 2/5 | 1.216 | 1.397, 1.163, 1.197, 1.075, 1.272 | 1.129 |
| Main | Korean 2K | 5/5 | 0/5 | 1.173 | 1.126, 1.129, 1.347, 1.169, 1.108 | 1.108 |
| Controlled | Code 4K | 3/3 | 2/3 | 1.134 | 1.135, 1.350, 0.951 | 1.081 |
| Controlled | Korean 2K | 3/3 | 1/3 | 1.168 | 1.164, 1.217, 1.124 | 1.123 |

The main series matched output only in code pairs 1–2. The controlled series matched in code pairs 1–2 and Korean pair 2. Draft acceptance differed in many other pairs, and controlled code pair 3 had B/A decode rate below 1. These measurements do not isolate the cost of the two Juud controls from changes in generated text and draft acceptance. The exact-output subsets are too small for a reliable speed estimate. No current advantage is claimed from this comparison.

`pairs.json` contains selected per-pair numerical metrics, SHA-256 hashes of each arm's synthetic request and generated output, build hashes, and sanitized settings. It excludes request and output text. Run `python verify.py` to recompute the table's geometric means and check the recorded A/B request and output hash equality. The hashes verify equality within these records; without the private text they cannot independently prove the text's hash. The run did not test answer quality, long context, H100, or multi-user throughput.
