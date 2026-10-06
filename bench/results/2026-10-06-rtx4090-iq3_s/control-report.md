# Strata와 Juud_engine: RTX 4090 비교 보고서

> **공개본:** PC 경로, 전체 요청·생성 문장, 서버 로그를 제외했습니다. 아래 원자료 SHA-256은 보관 중인 로컬 원본의 해시입니다. 공개 `summary.json`의 `source` 필드와 `source-correction.json`의 경로 필드는 비식별화되어 원본 해시와 다릅니다. 공개 `paired_metrics.jsonl`에서 쌍별 수치와 출력 해시 일치율을 다시 계산할 수 있습니다.

A는 Strata, B는 Juud_engine입니다. 양수의 paired gain은 B가 빠르다는 뜻입니다.
벤치 시작(UTC): 2026-10-06T03:36:44.106893+00:00 · 유효 요청쌍: 12/12

## 비교 조건과 출처

| 항목 | A: Strata | B: Juud_engine |
| --- | --- | --- |
| 소스 커밋 | `6f32ec070f23ced9f50e704d854d775da52591ab` | `312daafe01cf464f9bca1c52b34b161d3b7b3be2` |
| 작업 트리 변경 | False | False |
| BUILD source/version | local / 0.1.39 | local / 0.1.39 |
| BUILD 소스 지문 | `37013ae43048249b` | `d778c32e3b94fe1c` |
| CUDA 아키텍처 | [89] | [89] |
| BUILD.json SHA-256 | `37a33a796d22be2ee48746409085a42a85d7a7d4e62cfd25320bf7027e2f5a23` | `d51b1ea77cbb40fc1b0d55b883fb96d88b0c514c52424c9f22b1cc2495360a79` |

- 공유 pack 디렉터리: `iq3_s` (실제 경로는 manifest에 보존).
- 정규화 추론 설정 검증: 통과 (`296d0d3dbcd818150965f913649aaafeb61caf6a12195bb536f5425ca9316868`).
- 모델 확인 범위: 러너가 같은 pack·tokenizer 경로와 설정을 요구했습니다. 원본 GGUF의 로컬 SHA-256은 아래 장비 기록에 별도로 보존했습니다.
- BUILD CUDA 아키텍처 일치: 예. BUILD.json은 컴파일러 버전이나 실행 파일 해시를 보증하지 않습니다.


## 장비와 바이너리 지문

- GPU: NVIDIA GeForce RTX 4090, VRAM 24564 MiB, 드라이버 591.86, compute 8.9.
- CPU: 13th Gen Intel(R) Core(TM) i7-13700; 물리 RAM 137167679488 bytes; OS Microsoft Windows NT 10.0.22621.0.
- CUDA 13.0 V13.0.88; MSVC 19.44.35220 x64.
- Strata 실행 파일 SHA-256: `c12f2928ab95c5defc54a5cf9e3c4d9f1f2442dd60a0bc97e44a41c1fe1cd395`.
- Juud_engine 실행 파일 SHA-256: `e797b44993cbcff23d5cd686941c1f4a1b381545ea002bbb4f8d0a9940d5ed87`.
- IQ3_S 원본: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF` revision `ed59f92082b1e93c0e96d60a8b11aab089b52f09`.
- MTP 원본: `Qwen/Qwen3.8-Flash-Next` revision `de4b8e4d43b917e7706784d8bb445c9af86a3540`; 31개 텐서 manifest SHA-256 `6d0b9f960bde353913af870d2095304922d2218131943b3df6a8a0a253368975`.

모델 GGUF 파일은 다운로드 완료 후 로컬 SHA-256으로 재확인했습니다.

| GGUF 조각 | 바이트 | SHA-256 |
| --- | ---: | --- |
| Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf | 54817524224 | `4c1eb2ceb4915e1192f4f386021897bde56a97f40a0bb78bb86465e0f7d2aca3` |
| Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf | 28800138432 | `316b46f3a2dbd68c900f43136ab9449f9dcc3725dfd8c794847c204bc161e113` |

## Juud_engine 최적화 설정

아래 값은 manifest의 SHA-256과 일치하는 A/B 실행 설정 JSON의 `env` 항목입니다. 실행 프로세스 내부에서 환경변수를 다시 읽어 검증한 기록은 아닙니다.

| 환경변수 | A: Strata | B: Juud_engine |
| --- | --- | --- |
| `JUUD_POOL_ADAPTIVE_SPIN` | 명시적으로 해제 (null) | `1` |
| `JUUD_SKIP_UNUSED_ACTQ` | 명시적으로 해제 (null) | `1` |
| `STRATA_POOL_SPIN_US` | 명시적으로 해제 (null) | 명시적으로 해제 (null) |

- `JUUD_POOL_ADAPTIVE_SPIN=1`: CPU 전문가 작업의 단계에 따라 워커 대기 시간을 조정합니다. 명시적인 `STRATA_POOL_SPIN_US` 값이 있으면 고정 대기 정책이 우선합니다.
- `JUUD_SKIP_UNUSED_ACTQ=1`: 단일 GPU 구성에서 CPU 전문가 작업이 없는 토큰의 CPU 활성값 양자화를 생략합니다. 해당 작업이 실제로 발생했는지와 성능 효과는 이 설정값만으로 확인할 수 없습니다.
- 두 옵션 모두 기본값은 비활성입니다. A/B 설정에서 항목이 빠지면 부모 프로세스 환경을 상속할 수 있어 실제 적용 여부를 단정할 수 없습니다.

## 처리량과 지연

아래 수치는 같은 요청 SHA-256의 유효 A/B 쌍만 사용한 중앙값입니다. 향상률은 각 쌍의 비율을 먼저 계산한 뒤 중앙값을 취했습니다. 모델 시작 시간은 제외했습니다.

| 작업 | 유효쌍 | 입력 tok/s A → B (gain) | 출력 tok/s A → B (gain) | 첫 응답 초 A → B (gain) | 전체 초 A → B (gain) |
| --- | ---: | --- | --- | --- | --- |
| code-4096 | 3/3 | 2,301.12 → 2,307.35 (+0.0%) | 69.45 → 79.61 (+14.7%) | 1.80 → 1.80 (-0.3%) | 5.48 → 5.01 (+8.4%) |
| code-32768 | 3/3 | 4,417.48 → 4,408.39 (-0.3%) | 69.89 → 77.59 (+9.6%) | 7.49 → 7.51 (-0.6%) | 11.13 → 10.77 (+2.5%) |
| code-128000 | 3/3 | 4,186.10 → 4,174.86 (-0.3%) | 68.45 → 72.46 (+15.6%) | 30.78 → 30.86 (-0.2%) | 34.70 → 34.31 (+1.2%) |
| korean-2048 | 3/3 | 1,262.41 → 1,265.06 (+0.2%) | 49.34 → 56.41 (+14.2%) | 1.66 → 1.66 (-0.1%) | 6.82 → 6.18 (+9.2%) |

## 불완전 출력과 오류

- 전체 기대 요청쌍 12개 중 0개를 수치 계산에서 제외했습니다.
- 기록된 모든 요청쌍이 완료·토큰수·시간 검사와 각 출력의 무결성 해시 검사를 통과했습니다. A/B 출력의 상호 일치율은 아래 표에 따로 표시합니다.

## MTP 수용과 출력 일치

MTP 수용률은 유효 요청쌍에서 기록된 수용 토큰 수 / 제안 토큰 수입니다. 제안 수가 0이면 비율을 계산하지 않습니다.

| 작업 | A 수용/제안 | B 수용/제안 | 출력 해시 일치 |
| --- | ---: | ---: | ---: |
| code-4096 | 490/653 (75.0%) | 492/654 (75.2%) | 3/3 |
| code-32768 | 454/663 (68.5%) | 455/664 (68.5%) | 3/3 |
| code-128000 | 455/629 (72.3%) | 457/625 (73.1%) | 3/3 |
| korean-2048 | 362/564 (64.2%) | 364/562 (64.8%) | 3/3 |

[원본 Strata의 재현성 설명](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/DETAILS.md)에 따르면 greedy 출력도 IQ 전문가의 단일·다중 토큰 커널 반올림, draft window, 적응형 GPU 캐시와 PCIe 실행 위치에 따라 달라질 수 있습니다. 같은 요청과 출력 토큰 수라도 답변 및 MTP 수용률 차이는 처리 시간에 영향을 줄 수 있습니다. 해시 불일치만으로 기능 오류나 품질 차이를 단정할 수 없으며, 해시 일치는 품질 평가를 대신하지 않습니다.

## GPU·CPU·VRAM 관측 범위

기록된 장비명: GPU NVIDIA GeForce RTX 4090, CPU 13th Gen Intel(R) Core(TM) i7-13700.

아래 표는 러너가 요청 종료 후 `/metrics`에서 받은 **완료 무렵 단일 스냅샷**의 최소–최대입니다. 요청 전체 평균, 요청 중 최고치, 소비 에너지 또는 프로세스별 CPU 사용률이 아닙니다.

| 관측값 | A: Strata | B: Juud_engine |
| --- | --- | --- |
| GPU 사용률 | 100.0–100.0% (12개 완료 시점) | 99.0–100.0% (12개 완료 시점) |
| 시스템 CPU 사용률 | 61.3–66.9% (12개 완료 시점) | 7.2–19.2% (12개 완료 시점) |
| VRAM 사용량 | 23.0–23.0 GiB (12개 완료 시점) | 23.0–23.0 GiB (12개 완료 시점) |
| GPU 전력 | 152.4–179.3 W (12개 완료 시점) | 167.5–194.0 W (12개 완료 시점) |

별도의 `nvidia-smi` 폴링 기록은 `runs.jsonl`의 `gpu_sampling.file`에서 찾을 수 있습니다. 요청별 `gpu_sampling.by_gpu`의 평균·최소·최대는 **폴링 명령 구간이 요청과 겹친 샘플**의 집계이며, 정확한 요청 구간 평균·최고치나 소비 에너지가 아닙니다. 위 표에는 이 폴링 집계를 섞지 않았습니다.

## 판단과 한계

- 측정된 작업의 쌍별 출력 속도 gain 중앙값이 모두 양수입니다. 이는 이 모델·PC·설정·입력에 한정된 결과입니다.
- 이 러너는 합성 코드·한국어 입력과 단일 요청을 측정합니다. 품질, 장시간 안정성, 동시 요청 처리량, 실사용 전체를 대표하지 않습니다.
- 온도·클록·전력 제한의 시간 이력은 제공된 GPU 폴링 파일에서 확인해야 합니다. 모델 GGUF의 로컬 해시는 별도 환경 기록에 보존했습니다.

## 원자료 무결성

| 파일 | SHA-256 |
| --- | --- |
| summary.json (summary) | `922e637a4c17fef4d073cdb514ae69c7433d5d481b6cc06454dcc47b58af1fba` |
| runs.jsonl (runs) | `f45ee35cf1bf961cabffa929c6a56e4b266bca32e7b3749fc353b6b8020250e2` |
| manifest.json (manifest) | `1195f3191c45da1261d26f86ccee95f24a92ae98eb92c4f1768ab4817eae6535` |
| benchmark_environment.json (environment) | `6eee168165f9630f0821982e873263c12fb087e4adeb3572cb50a17485cfb730` |
| strata-BUILD.json (a_build) | `37a33a796d22be2ee48746409085a42a85d7a7d4e62cfd25320bf7027e2f5a23` |
| juud-BUILD.json (b_build) | `d51b1ea77cbb40fc1b0d55b883fb96d88b0c514c52424c9f22b1cc2495360a79` |
| strata-launch.json (a_launch) | `bb2cbc5edd63a252fdfe95671d8f1bd3813c01bf0744f228e5ccbe9ae4f4a9d2` |
| juud-launch.json (b_launch) | `77bd9304600a069f8efe5bb0675e7a068c13773338e6dda82d0c865e1b3c9079` |
