# x64 개선사항 전달 파일 목록

현재 전달물: `improved-performance.patch` 및 `performance-compat/`,
`apply-improvements.py`, `README-PERFORMANCE.md`. 아래는 기능별 파일 설명이며,
실제 적용에는 이 패치와 적용 도구를 사용합니다.

아래 표의 “x64 수정 필요”는 기존 로컬 ARM 작업본 기준입니다. 해당 로더·빌드·동봉
수정 코드는 전달용 패치에 별도로 포함했으며, x64 헬퍼 교차 컴파일은 통과했습니다.
x64 실기기 실행과 전체 릴리즈 검증은 남아 있습니다.

새 라이브러리·자체 DLL 추가는 허용하며, 최종 사용자가 별도 설치하지 않도록 배포물에 동봉한다는 조건입니다.

## 1. 이슈 본문

- `issue-report/ISSUE-X64-PERFORMANCE.md`

첫 줄은 제목, 나머지는 본문으로 사용합니다. 아래 소스 변경은 별도 패치 또는 PR로 전달합니다.

## 2. 신규 소스·리소스

| 파일 | 용도 | 현재 상태 |
| --- | --- | --- |
| `src/assets/preview.qml` | GPU 프리뷰 출력 | 있음 |
| `src/pipeline.py` | 제한된 큐로 단계 병행 | 있음 |
| `src/gpu_image.py` | GPU 이미지 변환 DLL 호출 | 있음. x64 로더 수정 필요 |
| `run/gpu_roi.c` | 자체 D3D11 변환 헬퍼 소스 | 있음. x64 빌드 검증 필요 |
| `run/build_gpu_roi.py` | 헬퍼 빌드 | 있음. 현재 ARM 전용이므로 x64 빌드 방식으로 수정 필요 |
| `src/tests/test_pipeline.py` | 큐·취소·수명 검사 | 있음 |
| `src/tests/test_gpu_image.py` | GPU 변환 정확도 검사 | 있음. x64 실기기 검증 필요 |

## 3. 기존 파일 수정분

아래는 파일 전체 덮어쓰기가 아니라 이번 기능에 해당하는 수정분만 전달합니다.

- `src/preview.py`: GPU 표시, 지연 이미지 변환, 최신 탐색 요청, 소스 교체·종료 정리.
- `src/profile_panel.py`: 크롭 갱신 제한, 숨김 처리, 가이드 영상, 메타데이터 기반 크기 처리.
- `src/app.py`: 타임라인 갱신, 탐색, 종료, 분석 옵션 전달 및 실제 처리 경로 표시.
- `src/media.py`: 영역·방향 검사, GPU 변환 진입점, 프레임 참조 순환 회수.
- `src/video_sampling.py`: 선택 후 이미지 변환, 독립 GPU 옵션, 파이프라인, CPU 복귀.
- `src/jacket_recognition.py`: 샘플 공급, 제한 큐 연결, 처리 완료 이미지 해제. 기존 경계 방식 유지.
- `src/recognition.py`: 옵션 전달.
- `src/workspace_ui.py`: 3번 화면의 세 옵션, 저장 및 작업 중 비활성화.
- `src/advanced_settings.py`: 옵션 위젯을 3번 화면에서 가져가지 않도록 수정.
- `src/tests/test_preview.py`, `src/tests/test_app.py`, `src/tests/test_recognition.py`: 해당 기능 회귀 검사.
- `run/pysidedeploy.spec`: Qt Quick/QML 및 배포 자산 설정. x64 DLL 포함과 ARM 산출물 제외 작업 필요.
- `run/build_windows.ps1`: x64 헬퍼 빌드·동봉·자산 검사 작업 필요.
- `.github/workflows/release.yml`: 컴파일러 준비·x64 빌드/검증 연결 작업 필요.
- `src/locales/en/LC_MESSAGES/arcadeclip.po`, `.mo`: 이번 UI 문구의 번역 추가 및 재생성 필요.

의존성 버전을 실제로 바꾸게 되는 경우에만 `pyproject.toml`, `uv.lock`도 함께 전달합니다. 원본의 x64 FFmpeg 동봉 설정은 유지합니다.

## 4. 재현·검증용 파일

필수 앱 실행 파일은 아니지만 검토자가 동작과 성능을 재현할 수 있도록 함께 전달하는 것을 권장합니다.

- `run/verify_preview.py`
- `run/verify_preview_lifecycle.py`
- `run/verify_gpu_analysis.py`
- `run/verify_analysis_options.py`
- `run/diagnose_decode_memory.py`

스크립트의 실행 안내·경로·출력 인코딩을 x64 환경에 맞춰 점검하고, 개인 영상 경로가 담긴 로그는 첨부에서 제외합니다. 기존 ARM 측정값을 x64 결과로 전달하지 않습니다.

## 5. 전달에서 제외

- 이미 게시한 동일 자켓 재사용·Free Play 보정의 구현, 프로필 옵션, 번역 및 전용 테스트.
- 기존 `issue-report/recognition-improvements.patch`: 위 별도 이슈의 패치이며 이번 기능은 포함하지 않습니다.
- `src/freeplay.py`: 이번 신규 전달 목록에서 제외. 대상 브랜치에 별도 기능이 이미 병합되어 있다면 옵션 연결의 호환성만 검토합니다.
- ARM 빌드·런처·의존성 잠금·패키징 스크립트와 ARM 배포 폴더.
- `src/ocr_bridge.py`, `src/ocr_worker.py`, ARM 실행을 위한 `src/text_recognition.py` 변경.
- `gpu_roi_arm64.dll`, `.pdb`, `.lib`, 캐시, 가상환경, 개인 로그 및 영상.

## 6. 코드 전달 형식과 최종 배포물

개발자에게는 이슈 본문과 **신규 파일을 포함한 `improved-performance.patch` 및 적용 순서 호환 도구**를 전달합니다. 공유 연결부의 충돌을 피하려면 `README-PERFORMANCE.md`에 안내한 적용 도구를 사용합니다. 현재 작업본 전체의 `git diff`나 소스 폴더 대신 분리한 패치를 전달하세요.

빌드 후 최종 사용자에게는 기존 방식의 `ArcadeClip-<version>-windows-x64.zip`을 전달합니다. ZIP에는 EXE뿐 아니라 Qt/QML·Python 패키지·FFmpeg·OCR 의존성과 **새로 빌드한 `gpu_roi_x64.dll`**을 포함합니다. 컴파일러는 사용자 배포물에 필요하지 않습니다.

현재 x64 헬퍼 DLL과 이 변경을 반영한 x64 ZIP은 아직 생성·검증하지 않았습니다. 기존 ARM 배포본을 x64 파일로 이름만 바꿔 전달할 수 없습니다.
