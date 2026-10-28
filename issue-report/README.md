# 이슈 제보용 파일

## 성능 개선 패치 전달

`improved-performance.patch`와 적용 순서 호환 도구를 준비했습니다.
적용 방법은 `README-PERFORMANCE.md`를 확인하세요. 기존 인식 패치와 함께
사용할 때는 `apply-improvements.py`가 적용 순서에 맞는 보정본을 선택합니다.
기존 `recognition-improvements.patch`는 변경하지 않았습니다.

## Windows x64 대상 통합 개선 제안

`ISSUE-X64-PERFORMANCE.md`의 첫 줄을 이슈 제목으로, 나머지를 GitHub Issues 본문으로 복사하세요.
ARM 포팅을 제외한 프리뷰·메모리·샘플링·GPU 옵션·파이프라인 개선을 정리했습니다.
이미 게시한 동일 자켓 판독 재사용·Free Play 보정은 이번 통합 제안에서 제외했습니다.
x64 GPU 헬퍼 및 배포 검증은 완료된 것으로 표시하지 않고 릴리즈 조건으로 명시했습니다.
이 문서는 이슈 초안이며, 이슈 게시나 x64 릴리즈 빌드를 실행한 것은 아닙니다.

## 기존 인식 개선 제안

- `ISSUE.md`: 복사해서 GitHub 이슈 본문에 붙여 넣을 수 있는 제보 초안.
- `recognition-improvements.patch`: 이번 곡 판독 개선과 Free Play 보정만 담은 패치. 기존 ARM64 포팅 변경 제외.
- `patch-manifest.json`: 기준 커밋, 포함 파일, 패치 SHA-256, 원본 적용 검사 결과.
- `matching-benchmark.json`: 합성 자켓 비교 실측값. 영상 디코딩과 OCR은 포함하지 않음.

패치는 `9110b4d71cda511ac6ee3ed5b165349988de0bdb` 기준입니다. 해당 버전의 별도 작업 복사본에서 다음과 같이 확인하고 적용할 수 있습니다.

```sh
git apply --check recognition-improvements.patch
git apply recognition-improvements.patch
```

GitHub에서 `.patch` 첨부를 허용하지 않으면 파일명 끝에 `.txt`를 붙이거나 이 폴더를 ZIP으로 첨부하세요. ARM64 배포본을 제보에 첨부할 필요는 없습니다.

로컬 실행본은 `dist/ArcadeClip-arm64/ArcadeClip.exe`입니다. 폴더 전체가 필요하며 OCR은 기존 ARM64 배포 구조에 따라 x64 보조 런타임을 사용합니다. 새 파일 이름의 ZIP은 `dist/ArcadeClip-0.2.1-windows-arm64-recognition-improved.zip`입니다. 기존 portable ZIP은 이전 빌드 그대로 남겨두었습니다.

Free Play 보정은 Settings → 인식 → 글자 영역에서 켜고, 플레이 중 1P 달성률 영역을 지정한 후 사용하세요. 프로필 저장으로 유지할 수 있습니다. 상세 동작과 한계는 `ISSUE.md`에 적었습니다.
