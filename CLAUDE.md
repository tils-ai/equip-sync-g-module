# CLAUDE.md — equip-sync-g-module (가먼트 프린터)

이 레포의 설계·운영 문서는 **`dps-store`** 프로젝트에서 통합 관리한다. Claude 세션을 이 레포에서 실행하더라도 그쪽 문서를 우선 참조하라.

## 신규 담당자: 시작 가이드

설계·운영 문서는 `dps-store`(비공개)의 프린터 문서 허브에 모여 있다. 그 허브 인덱스에 **"가먼트 프린터
신규 담당자"** 섹션이 있고, 읽어야 할 문서가 순서대로 정리돼 있다. **다른 문서를 무작위로 열지 말고
그 순서를 따르라.**

워크스페이스 루트 — 두 레포의 상위 디렉토리 — 에서 세션을 열면 허브가 함께 보인다. 이 레포 단독으로
세션을 열면 문서가 보이지 않으므로 권장하지 않는다.

> ⚠ **이 레포는 공개(PUBLIC)다.** 문서 목록이나 파일 경로를 이 파일에 옮겨 적지 않는다.
> 날짜 기반 파일명은 그 자체로 내부 설계 이력을 드러낸다.

## 벤더 자산 (신규 담당자)

본 모듈은 제조사 CLI 실행 파일과 API 라이브러리를 사용한다. 계약상 배포는 허가돼 있으나
**원본 파일명을 공개 레포에 텍스트로 남기지 않는다.**

레포에는 가명 바이너리만 추적된다.

```
vendor/cli_legacy.bin·lib   가명 (추적됨)
vendor/cli_pro.bin·lib      가명 (추적됨)
        ↓ scripts/restore_vendor.py
.source/                    복원 결과 (git 미추적)
```

**인계받을 것은 없다.** 가명 바이너리가 원본과 바이트 단위로 같은 사본이라, 클론 후
`python scripts/restore_vendor.py` 한 번이면 `.source/` 가 만들어진다. 실행 파일은 중립
이름으로, 라이브러리는 **자신의 PE export 이름**으로 복원된다.

- 별도 매핑 파일이나 CI secret 은 필요 없다. `vendor/.dll_manifest` 는 벤더가 export 이름과
  다른 파일명을 요구할 때만 쓰는 **선택적 오버라이드**이고, 없는 것이 정상이다
- **릴리즈 EXE 안에는 임베드되지만 설치 폴더에 파일로 드러나지 않는다.**
  PyInstaller onefile `--add-data ".source;.source"` 로 들어간다
- 제조사 커맨드라인 가이드 PDF 는 `vendor/` 에 없어 복원되지 않는다. 옵션을 확인할 일이
  있으면 사내 채널로 별도 요청한다 (코드는 쓰지 않는다)
- `.history/` 도 git 미추적 (IDE 작업 이력)

CLI 옵션 사용법은 문서 허브의 커맨드라인 옵션 분석 문서를 본다.

## 모듈 개요

- Brother GTX-4 가먼트 프린터 + 일반 작업지시서 프린터 자동 출력 Windows 프로그램
- Watcher + Agent 통합 단일 EXE (PyInstaller)
- 빌드 산출물: `equip-sync-g-vX.Y.Z.exe` (태그 push 시 GitHub Actions 자동 빌드)
- **두 종 출력**(2026-05-18~):
  - **가먼트 디자인**(PNG/PDF) → GTX-4 가먼트 프린터 (mode: `direct` | `gtx4cmd`)
  - **작업지시서**(PDF) → 일반 A4 레이저/잉크젯 프린터 — reportlab + qrcode로 클라이언트가 PDF 즉시 조립
- 두 출력은 **독립 ON/OFF 토글** (`config.ini` `[printer] garment_enabled` / `work_order_enabled`)
- 다중 가먼트 프린터 지원: `[printer] garment_name`에 쉼표로 구분

## 디렉토리 구조 (2026-05-18 평탄화)

```
equip-sync-g-module/
├── .github/workflows/build.yml    # tag push → 자동 빌드 & Release
├── scripts/restore_vendor.py      # vendor/ 가명 → .source/ 원본 이름 복원
├── vendor/                        # 벤더 자산 가명 바이너리 (추적됨)
├── .source/                       # vendor/ 복원 결과 — 대외비, git 미추적
├── assets/fonts/                  # Pretendard 번들 (**TTF** — reportlab 이 CFF .otf 를 못 읽어 임베딩 실패함)
├── gui/                           # 슬라이드 패널, 헤더, 카드, 로그 박스
│   ├── app.py
│   ├── settings_panel.py          # 프린터명 + 목록 OptionMenu + 새로고침
│   └── ...
├── main.py                        # 진입점
├── config.py                      # config.ini 로드·자동 생성 (PRINTER_NAMES 다중 지원)
├── printer.py                     # win32 출력 + list_printers()
├── agent.py                       # API 풀링 → 디자인+지시서 두 종 출력
├── api_client.py                  # mark_printed/failed에 target("garment"|"workOrder") 파라미터
├── auth.py                        # Device Auth
├── watcher.py                     # 폴더 감시 모드
├── processor.py                   # 가먼트 디자인 출력 흐름 (direct / gtx4cmd)
├── work_order_builder.py          # 작업지시서 PDF 조립 (reportlab + qrcode, 폰트: 번들 TTF → 맑은 고딕 → CID)
├── gtx4cmd.py                     # 벤더 CLI 래퍼
├── xml_builder.py                 # 벤더 CLI XML 파라미터 빌드
├── build.bat                      # PyInstaller + --collect-all reportlab/qrcode 포함
├── requirements.txt               # reportlab, qrcode 추가
└── CLAUDE.md
```

### 두 종 출력 흐름 (2026-05-18~)

```
[GET /api/printer/garment] → jobs[]
  · garmentPending, workOrderPending (서버 sub status)
  · workOrder: { tenantName, brandName, printedBy, workUrl, thumbnailUrls } (작업지시서 메타)

[agent._process_job(job)]
  ├─ 디자인 PNG/PDF 다운로드 (양쪽 출력 모두 필요)
  ├─ do_work_order = workOrderPending && config.WORK_ORDER_ENABLED && config.WORK_ORDER_PRINTER_NAME
  ├─ do_garment   = garmentPending   && config.GARMENT_ENABLED   && config.GARMENT_PRINTER_NAME
  │
  ├─ [지시서 먼저]
  │     build_work_order_pdf() → printer.print_pdf_general(일반 프린터)
  │     POST /api/printer/garment/{id}/printed  body: {"target": "workOrder"}
  │
  └─ [가먼트 나중, quantity번 반복]
        processor.process_file() → direct 또는 gtx4cmd
        POST /api/printer/garment/{id}/printed  body: {"target": "garment"}
```

토글 OFF인 출력은 해당 sub status를 PENDING으로 그대로 유지 → 다른 PC(ON 상태)가 처리.

## 개발·릴리즈 흐름

1. 로컬에서 코드 수정 (`python3 -m py_compile` 로 macOS에서 문법 검증 가능)
2. `dps-store/CLAUDE.md`의 커밋 규칙 동일 적용 (관련 파일 3개씩, `feat:`/`fix:`/`refactor:`)
3. `git tag vX.Y.Z && git push origin vX.Y.Z` → GitHub Actions가 단일 EXE 빌드 + Release 자동 생성
4. 과거 태그/릴리즈는 최신 2개만 유지 (`gh release delete <tag> --cleanup-tag --yes`)

## 서버 측 변경이 필요한 경우

가먼트 출력 큐·API 명세는 `dps-store`에 있으므로 양쪽 동시 변경이 필요할 수 있다. 그 경우:
- 서버의 가먼트 프린터 API 라우트와 본 모듈의 `agent.py` / `api_client.py` 를 함께 본다
- API 인터페이스 변경 시 문서 허브의 가먼트 API 명세를 동기 업데이트
