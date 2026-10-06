# Paired Strata and Juud_engine benchmark

`juud_compare.py` measures the **same Qwen3.8-Flash-Next IQ3_S pack on the same PC** through each engine's local Chat Completions API. It runs one server at a time. The order is A, B, B, A across successive pairs to reduce time and temperature drift. A is stock Strata; B is Juud_engine. Model loading is timed separately and excluded from request latency.

This tool has **not** been run against a model as part of its creation. The repository must not claim a percentage improvement until `runs.jsonl` contains real paired results from the RTX 4090.

## Prepare the two builds

Pin the Strata commit and the Juud_engine commit. Build both using the same compiler, CUDA version and build options. Use the same model files and pack, exact `strata-iq3_s.json` settings, context, KV type, MTP draft vocabulary, expert profile, cache size, prefill setting, and vision setting. Keep both servers on loopback, with no API key during this local benchmark. Each server needs its own checkout and prepared Python environment; both can point to the same model data. Do not start either server manually.

Create two local JSON files outside the repository, for example `strata-launch.json` and `juud-launch.json`. Each needs an argument array, a working directory and the same loopback URL. Example for Strata on Windows:

```json
{
  "command": [
    "C:/path/to/Strata/.venv/Scripts/python.exe",
    "serve/server.py", "--engine", "strata",
    "--config", "strata-iq3_s.json",
    "--host", "127.0.0.1", "--port", "18080"
  ],
  "cwd": "C:/path/to/Strata",
  "url": "http://127.0.0.1:18080"
}
```

For Juud_engine, change the Python executable and `cwd` to the Juud checkout. Keep `url` and port identical; the harness starts the servers serially. An optional `"env": {"NAME": "value", "REMOVE_ME": null}` object sets or unsets environment variables for that server; the child engine inherits them. For the adaptive CPU pool experiment, put `"env": {"STRATA_POOL_SPIN_US": null, "JUUD_POOL_ADAPTIVE_SPIN": "1"}` in the Juud launch JSON and clear both variables in the Strata launch JSON. Avoid secrets in the JSON files because their hashes and paths appear in the manifest; review all logs and configurations before publishing.

## Run

From the Juud_engine checkout, use its prepared Python environment or another Python with Strata's `serve.frontend` dependencies available:

```powershell
python bench/juud_compare.py run `
  --a C:/path/to/strata-launch.json `
  --b C:/path/to/juud-launch.json `
  --root C:/path/to/Strata `
  --pack D:/Strata-data/packs/iq3_s `
  --out C:/path/to/results/rtx4090-iq3s-01 `
  --pairs 5
```

`--root` supplies Strata's tokenizer and chat template for sizing prompts. `--pack` is the **shared** IQ3_S pack. The harness verifies both servers report the expected prompt token count. The output directory must be new. Default workloads are 4,096, 32,768 and 128,000 token synthetic Python prompts plus a 2,048 token Korean chat prompt. Each requests 256 generated tokens with `temperature: 0`, `reasoning_effort: none`, streaming and usage included. The early nonce makes prefix reuse observable and normally zero. Pass `--targets 4096,32768` if the configured context cannot fit the 128,000 token prompt plus output.

Each launch gets a small excluded warm-up request, then one request per workload. The harness saves every request body and SHA-256 hash, HTTP stream chunks, output text, engine timings, cache hit rate, draft acceptance where available, token counts and failure flags. It checks that a measured request produces the full 256 tokens, has no reused prefix, and reports valid engine timings. An early EOS or failure stays in the raw data but is excluded from the paired median.

Before starting, the harness reads both `strata-iq3_s.json` files and requires matching inference settings, the shared pack and tokenizer, and different engine executables. It compares the expert-profile file by SHA-256, so identical copies in different checkouts are allowed. Vision and experimental speed projection must be off. It also requires enough configured context for the longest prompt plus the output cap and Strata's 8-token margin, then checks each running server's `/health.max_context` before sending measured requests. A warm-up must return nonempty output and usable `/metrics` timing; ending before its 16-token cap is allowed.

Files in the output directory:

- `runs.jsonl`: every measured request, including failures and full raw response chunks.
- `summary.json` and `summary.md`: paired A/B medians and per-pair gains.
- `requests/pair-*.json`: exact workload requests and SHA-256 hashes.
- `server-logs/*`: launch logs, readiness snapshot and warm-up results.
- `manifest.json`: benchmark options, host/Python details, source commits and dirty state, and launch configuration hashes.

If a run stops early, regenerate the summary from its saved measured rows:

```powershell
python bench/juud_compare.py summarize --out C:/path/to/results/rtx4090-iq3s-01
```

## Interpret and publish

Prefill throughput is freshly processed prompt tokens divided by engine `prompt_ms`; decode throughput is engine generated tokens divided by engine `decode_ms`. TTFT is from sending the request to the first nonempty text or reasoning delta; total latency ends at stream completion. The table's positive percentage means Juud is faster: `B/A - 1` for throughput and `1 - B/A` for latency. Report each workload separately. Do not use total request time to calculate decode tok/s.

The synthetic Python prompts test a narrow workload. The Korean prompt gives another text pattern but is still synthetic. Keep conclusions scoped to these inputs. Save GPU clocks, power, temperature and VRAM sampling alongside `runs.jsonl`; note other workloads running on the PC. Check that the same model files and source/compiler settings were used, inspect output text and MTP draft acceptance, and run separate correctness checks such as `tools/needle_bench.py` and a coding task with tests. A different answer can change speculative draft acceptance even when input bytes match. An exact output match is recorded as a diagnostic, not assumed to be required for every valid answer.

The methodology follows Strata's [community benchmark guide](../docs/COMMUNITY_BENCHMARKS.md) and adapts its [RTX 5090 reproducible harness](results/2026-09-30-community-rtx-5090/benchmark.py).
