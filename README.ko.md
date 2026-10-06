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

이 PC의 RTX 4090에서 **Strata보다 빠르다는 실측 결과는 아직 없습니다.** 두 옵션을 함께 켠 실험만으로는
각 옵션의 효과를 따로 판단할 수도 없습니다. [영문 README](README.md)에 보존된 원본 Strata의 속도 수치는 Juud_engine 측정값이 아닙니다.

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

## RTX 4090 비교 계획과 원자료

원본 Strata와 Juud_engine을 별도로 빌드한 뒤, 같은 Qwen3.8-Flash-Next IQ3_S 모델 파일·설정·요청을
RTX 4090 PC에서 번갈아 실행할 계획입니다. 한 번에 서버 하나만 띄우고, 완료되지 않은 출력과 오류는
원자료에 남기되 유효한 A/B 요청쌍의 성능 계산에서는 제외합니다. 비교 실행법은
[벤치마크 안내](bench/README.md), 아직 비어 있는 결과표와 발표 기준은
[평가 기록](docs/JUUD_EVALUATION.md)에 있습니다.

실행 후에는 `runs.jsonl`, `summary.json`, `manifest.json`, 요청 파일, 서버 로그와 GPU 샘플링 기록을
함께 보존할 예정입니다. **현재 공개할 Juud_engine 대 Strata 성능 수치나 결과 원자료는 없습니다.**
속도 향상이 없거나 느려지는 경우에도 그 결과를 그대로 표시합니다.

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
