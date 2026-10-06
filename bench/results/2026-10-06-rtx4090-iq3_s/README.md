# RTX 4090 실측: Strata와 Juud_engine

2026-10-06에 Qwen3.8-Flash-Next IQ3_S를 RTX 4090 한 장에서 비교했습니다. A는 원본
[Strata `6f32ec0`](https://github.com/Niko1221/Strata/tree/6f32ec070f23ced9f50e704d854d775da52591ab),
B는 이 저장소의 Juud_engine입니다. 같은 모델 팩·토크나이저와 요청을 사용하고, 서버를 한 번에 하나씩
실행했습니다. 모든 측정 요청은 256토큰을 생성했고 캐시 재사용은 0이었습니다. Juud의 두 옵션
`JUUD_POOL_ADAPTIVE_SPIN=1`과 `JUUD_SKIP_UNUSED_ACTQ=1`은 B에만 함께 적용했습니다.

표의 향상률은 **같은 요청 A/B 쌍의 비율을 먼저 계산한 뒤 그 중앙값**입니다. 양수는 Juud가 빠르다는
뜻이며 모델 시작 시간은 제외했습니다.

| 작업 | 기본 조건 출력 tok/s 향상, 5쌍 | 기본 조건 전체 지연 개선 | 출력 일치 보조 조건 출력 tok/s 향상, 3쌍 | 보조 조건 전체 지연 개선 |
| --- | ---: | ---: | ---: | ---: |
| 코드 4K 입력 | +9.1% | +5.6% | +14.7% | +8.4% |
| 코드 32K 입력 | +3.6% | +1.4% | +9.6% | +2.5% |
| 코드 128K 입력 | +3.1% | +0.5% | +15.6% | +1.2% |
| 한국어 2K 입력 | +7.5% | +4.3% | +14.2% | +9.2% |

기본 조건 20쌍 중 A/B의 **생성 문장이 같은 쌍은 5개**였습니다. 다른 답변과 MTP 수용률이 처리
속도에 영향을 줄 수 있으므로 위 수치를 코드 수정만의 순수 효과로 볼 수 없습니다. 원본 Strata도
[greedy 출력의 비결정성](https://github.com/Niko1221/Strata/blob/6f32ec070f23ced9f50e704d854d775da52591ab/docs/DETAILS.md)을
설명합니다. 별도 보조 실험에서는 **양쪽 모두** `STRATA_IQ_MT_MIN=1`, `--prompt-cache 0`,
`--adapt-swaps 0`, `--pcie-frac 0`을 사용했고 **12/12쌍의 생성 문장이 일치**했습니다. 이 설정은
기본 조건과 CPU·PCIe 동작이 다르므로 두 실험의 수치를 합치지 않습니다. 두 Juud 옵션 중 어느 하나의
기여도를 분리한 실험도 아닙니다.

## 공개 자료와 비공개 원본

공개 자료는 검증 가능한 **쌍별 수치와 해시**, 요약, 보고서로 제한했습니다. 원본 요청·생성 문장,
서버 로그, GPU 폴링 기록, PC 사용자 경로가 들어 있는 전체 캡처는 로컬 ZIP으로 보관하며 GitHub에는
게시하지 않았습니다. 공개용 투영 과정에서 각 출력의 SHA-256 무결성을 다시 확인했습니다. 원본 파일의
SHA-256과 공개 파일의 SHA-256은 [출처 기록](public-provenance.json)에 구분해 적었습니다.

| 자료 | 기본 조건 | 출력 일치 보조 조건 |
| --- | --- | --- |
| 상세 보고서 | [primary-report.md](primary-report.md) | [control-report.md](control-report.md) |
| 쌍별 측정값·요청 및 출력 해시 | [paired_metrics.jsonl](primary/paired_metrics.jsonl) | [paired_metrics.jsonl](control/paired_metrics.jsonl) |
| 요약 수치 | [summary.json](primary/summary.json) | [summary.json](control/summary.json) |
| 공개 매니페스트 | [manifest-public.json](primary/manifest-public.json) | [manifest-public.json](control/manifest-public.json) |

[장비·바이너리·모델 해시](benchmark_environment.json), [Strata 빌드 지문](strata-BUILD.json),
[Juud 빌드 지문](juud-BUILD.json), [모델 조각 1](model-verification-shard1.json),
[모델 조각 2](model-verification-shard2.json)도 공개합니다. 기본 실험의 B 소스 커밋은 측정 당시
Windows `safe.directory` 캡처 오류로 누락되어 측정 직후 동일 바이너리 해시와 깨끗한 작업 트리를
확인해 보완했습니다. [경로를 지운 수정 감사 기록](primary/source-correction.json)을 참조하세요.

공개 쌍별 수치에서 중앙값·향상률·출력 해시 일치율을 다시 계산하려면 이 저장소 루트에서 실행하세요.

```powershell
python bench/verify_public_metrics.py bench/results/2026-10-06-rtx4090-iq3_s/primary
python bench/verify_public_metrics.py bench/results/2026-10-06-rtx4090-iq3_s/control
```

전체 캡처로 같은 보고서를 재생성하는 스크립트는
[render_juud_report.py](../../render_juud_report.py)입니다. 공개 자료만으로는 원본 생성 문장과
서버 로그의 내용, 출력 품질을 검증할 수 없습니다. 합성 단일 요청 3~5쌍의 결과이며 동시 처리량,
장기 안정성, 다른 모델이나 GPU의 성능까지 입증하지 않습니다.
[H100 안내](../../../docs/H100_SINGLE_GPU.md)는 용량과 빌드 검토이며 H100 실측은 아닙니다.
