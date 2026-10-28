# 성능 개선 패치와 적용 순서 호환

## 전달 파일

- `improved-performance.patch`: 원본 기준의 성능 개선만 포함한 패치.
- `recognition-improvements.patch`: 기존에 게시한 인식 개선 패치. 내용과 SHA-256을 변경하지 않았습니다.
- `apply-improvements.py`: 현재 적용 상태를 확인하여 필요한 패치를 선택하는 도구. Python 표준 라이브러리와 Git만 사용합니다.
- `performance-compat/`: 적용 순서에 따른 보정 패치 두 개와 상태·체크섬 기록.
- `improved-performance-manifest.json`: 기준 커밋과 검증 기록.

기준 커밋: `9110b4d71cda511ac6ee3ed5b165349988de0bdb`.

## 권장 적용

위 파일들의 상대 경로를 유지해 ZIP을 풀고, 적용할 프로젝트 경로를 지정합니다.

```powershell
python apply-improvements.py performance --repo C:\path\to\ArcadeClip
python apply-improvements.py recognition --repo C:\path\to\ArcadeClip
```

반대 순서도 가능합니다.

```powershell
python apply-improvements.py recognition --repo C:\path\to\ArcadeClip
python apply-improvements.py performance --repo C:\path\to\ArcadeClip
```

두 기능을 한 번에 적용하려면 다음과 같습니다.

```powershell
python apply-improvements.py both --repo C:\path\to\ArcadeClip
```

`--check`를 추가하면 파일을 수정하지 않고 지원되는 상태인지와 적용 계획을 확인합니다. 이미 적용한 기능을 다시 요청하면 건너뜁니다. 기존 패치를 Git으로 먼저 적용한 경우에도 기록된 파일 상태와 같으면 인식합니다.

다른 수정이 섞여 지원 상태와 다르면 중단하며, 파일을 강제로 덮어쓰거나 Git reset을 실행하지 않습니다. 줄바꿈 CRLF/LF 차이는 허용합니다. 임의의 최신 브랜치나 사용자가 변경한 코드까지 무조건 병합하는 도구는 아닙니다.

## 수동 적용

원본에서 성능 패치만 적용할 때:

```powershell
git apply --check path/to/improved-performance.patch
git apply path/to/improved-performance.patch
```

기존 인식 패치를 먼저 적용했다면 두 번째에는 `performance-compat/performance-after-recognition.patch`를 사용합니다. 성능 패치를 먼저 적용했다면 두 번째에는 `performance-compat/recognition-after-performance.patch`를 사용합니다. 매번 `git apply --check` 후 적용하세요.

**원본용 두 패치를 같은 명령으로 순서만 바꾸어 적용하는 것은 보장하지 않습니다.** 같은 함수의 연결부가 달라지기 때문입니다. 제공된 적용 도구 또는 해당 방향의 보정 패치를 사용해야 합니다. 보정본은 기존 변경을 다시 덮어쓰지 않고 아직 없는 변경과 공유 연결부의 조정만 반영합니다.

## 포함·제외 및 x64 상태

성능 패치는 GPU 프리뷰, 지연 스냅샷, 크롭/탐색 최적화, 메모리 회수, 독립 분석 GPU 옵션, 제한된 파이프라인, x64 D3D11 헬퍼 소스·빌드·동봉 연결을 포함합니다. 동일 자켓 재사용·Free Play 기능 자체와 ARM 포팅·OCR 브리지는 포함하지 않습니다.

인식 패치 뒤 성능 패치를 적용하거나 그 반대로 적용한 최종 소스는 동일함을 검사했습니다. 기존 경계 인식은 유지하며 CPU 단일 작업자의 경계 버퍼 경로에서는 앞서 읽기를 제한합니다. 별도 인식 패치의 Free Play 변환 동작은 그대로 유지합니다.

헬퍼 DLL은 빌드 시 생성합니다. x64 실기기의 GPU 실행 및 전체 Nuitka 릴리즈는 별도 검증이 필요하며 완료된 것으로 표시하지 않습니다. 기존 ARM 배포본을 x64 릴리즈로 제공하지 않습니다.

검증 결과: 두 적용 순서의 최종 파일 동일성, 적용 도구의 중복 실행 및 알 수 없는 수정 보호를 확인했습니다. 분리된 성능 코드 테스트 35개와 결합 코드 테스트 43개가 통과했습니다(ARM64 Python에서 수행한 공통 코드 검사). Zig를 이용한 x64 헬퍼 교차 컴파일과 PE 아키텍처 검사도 통과했습니다. x64 GPU 실제 실행이나 MSVC/Nuitka 전체 빌드 완료를 뜻하지 않습니다.

영어 번역 원본 `.po`는 포함되며 기존 빌드 단계가 `.mo`를 생성합니다. 소스에서 실행할 때 새 번역을 사용하려면 `python run/compile_messages.py`를 실행하세요. 두 패치를 모두 적용한 뒤 실행해야 적용 도구의 기존 상태 검사가 유지됩니다.
