# Juud_engine

[English](README.md) · **한국어**

Juud_engine은 [Strata](https://github.com/Niko1221/Strata)를 바탕으로
[Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next)를 로컬에서 실행하는 실험용 엔진입니다.
기준 소스는 Strata v0.1.39의
[`6f32ec070f23ced9f50e704d854d775da52591ab`](https://github.com/Niko1221/Strata/tree/6f32ec070f23ced9f50e704d854d775da52591ab)이며,
원본의 MIT 저작권 표시와 라이선스를 유지합니다.

## 추가한 두 최적화

두 기능은 **기본적으로 꺼져** 있으며, 이 저장소의 소스로 엔진을 빌드해야 사용할 수 있습니다.

| 환경변수 | 동작 |
| --- | --- |
| `JUUD_POOL_ADAPTIVE_SPIN=1` | CPU 전문가 배치의 gate/up 단계와 down 단계 사이에는 기존 20ms 대기 정책을 유지하고, 배치가 끝난 뒤에는 워커의 회전 대기를 100µs로 줄입니다. `STRATA_POOL_SPIN_US`를 명시하면 그 고정값이 우선합니다. |
| `JUUD_SKIP_UNUSED_ACTQ=1` | 단일 GPU 경로에서 한 토큰의 선택된 전문가가 모두 GPU에 있을 때, CPU 전문가 작업에서 사용하지 않을 활성값 양자화를 생략합니다. |

이 PC의 RTX 4090에서 원본 Strata와 같은 IQ3_S 모델로 [A/B 실측](bench/results/2026-10-06-rtx4090-iq3_s/README.md)을 마쳤습니다.
두 옵션을 **함께** 켠 결과이므로 어느 옵션이 얼마나 기여했는지는 알 수 없습니다. 아래 결과는 이 장비와
설정에서만 확인한 값입니다. [영문 README](README.md)에 보존된 원본 Strata의 다른 PC 속도 수치는
Juud_engine 측정값이 아닙니다.

## Windows에서 실행

이 저장소의 실행 파일을 빌드하고 모델 설치를 마친 다음 PowerShell에서 다음처럼 옵션을 켤 수 있습니다.

```powershell
.\START-HERE.bat --build --no-start
$env:JUUD_POOL_ADAPTIVE_SPIN = '1'
$env:JUUD_SKIP_UNUSED_ACTQ = '1'
.\START-HERE.bat
```

`engine/strata.exe`를 파일 탐색기에서 직접 열면 CUDA DLL 경로가 빠질 수 있습니다. 위 시작 스크립트는
서버 설정의 CUDA 라이브러리 경로를 엔진 프로세스에 전달합니다.

## RTX 4090 실측 비교

2026-10-06에 같은 PC(RTX 4090, i7-13700), 같은 Qwen3.8-Flash-Next IQ3_S 팩과 요청으로 원본 Strata(A)와
Juud_engine(B)를 번갈아 실행했습니다. 기본 설정의 **5쌍씩 4개 작업, 총 20개 유효 요청쌍**에서
출력 속도의 쌍별 향상률 중앙값은 아래와 같습니다. 속도와 지연 시간의 A/B 중앙값 및 공개 쌍별 수치는
[비교 보고서](bench/results/2026-10-06-rtx4090-iq3_s/README.md)에 있습니다. 전체 요청·생성 문장과
서버 로그가 포함된 원본은 PC 경로 노출을 피하기 위해 로컬 ZIP으로 따로 보관했습니다.

| 작업 | Strata → Juud 출력 tok/s 중앙값 | 쌍별 출력 속도 향상률 중앙값 | 쌍별 전체 지연 개선 중앙값 | A/B 출력 해시 일치 |
| --- | ---: | ---: | ---: | ---: |
| 코드 4K 입력 | 76.14 → 80.25 | +9.1% | +5.6% | 4/5 |
| 코드 32K 입력 | 99.32 → 100.31 | +3.6% | +1.4% | 1/5 |
| 코드 128K 입력 | 97.28 → 100.76 | +3.1% | +0.5% | 0/5 |
| 한국어 2K 입력 | 77.63 → 83.42 | +7.5% | +4.3% | 0/5 |

기본 설정에서는 같은 요청이라도 A/B의 생성 문장이 다를 수 있었습니다. 출력 경로와 MTP 수용 차이가
속도에 영향을 줄 수 있어 위 향상률을 두 코드 변경만의 순수 효과로 해석하면 안 됩니다. Strata의
재현성 권장 설정으로 양쪽 출력을 같게 만든 **별도 보조 실험**에서는 3쌍씩 4개 작업의 출력 해시가
모두 일치했고, 쌍별 출력 속도 향상률 중앙값이 코드 4K +14.7%, 32K +9.6%, 128K +15.6%, 한국어 2K
+14.2%였습니다. 이 보조 실험은 기본 설정과 캐시·PCIe 옵션이 다르므로 두 실험의 속도를 합치거나
직접 대조하지 않습니다.

[평가 기록](docs/JUUD_EVALUATION.md)에 장비, 빌드, 모델 해시와 각 실험의 한계를 정리했습니다.
비교 재실행 방법은 [벤치마크 안내](bench/README.md)를 보세요.

## H100 94 GB 한 장

[H100 단일 GPU 안내](docs/H100_SINGLE_GPU.md)는 양자화 모델 크기와 Strata의 메모리 배치에 근거한
용량 추정과 빌드·검증 절차입니다. H100에서 이 포크의 실행 성공, 처리량, 지연 시간은 **아직 측정하거나
검증하지 않았습니다.** 94 GB VRAM이 있어도 모델의 전문가와 긴 문맥 처리에는 시스템 RAM과 SSD가
필요할 수 있습니다. 안내서의 모델 크기를 실제 VRAM 사용량이나 속도로 해석하지 마세요.

## 소스와 모델 라이선스

Strata 기반 **엔진 소스**의 라이선스는 [MIT](LICENSE)입니다. 전체 모델 가중치와 IQ3_S 팩은 이 저장소에
포함되지 않으며 별도로 받아야 합니다. 공식 **Qwen3.8-Flash-Next 모델**에는
[Qwen Community License 1.0](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/LICENSE)이 적용됩니다.
상업적 Model-as-a-Service 또는 AI 업무 보조 서비스 사업에는 별도 라이선스 조건이 있으며,
제3자에게 모델·출력·모델 기능을 제공하지 않는 내부 사용에는 그 조건이 적용되지 않습니다.
사용할 모델과 양자화 파일의 정확한 배포 조건을 확인하세요. 원본 Strata에서 물려받은
`data/experimental-speed-projection`의 작은 GGUF 제어 벡터에도 Qwen 라이선스가 적용됩니다.
다른 서드파티 코드와 자산의 고유 고지도 유지됩니다.
