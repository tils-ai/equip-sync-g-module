# CLAUDE.md — equip-sync-g-module (가먼트 프린터)

이 레포의 설계·운영 문서는 **`dps-store`** 프로젝트에서 통합 관리한다. Claude 세션을 이 레포에서 실행하더라도 아래 문서를 우선 참조하라.

## 신규 담당자: 시작 가이드

이 모듈에 합류했다면 아래 순서로 읽으면 작업을 시작할 수 있다. **다른 문서를 무작위로 열지 말고 이 순서대로 시작하라.**

1. `dps-store/docs/print/README.md` — 전체 인덱스 + "가먼트 프린터 신규 담당자" 섹션
2. `dps-store/docs/print/20260511-equipment-gui-unification.md` — 3개 모듈 공통 아키텍처 (Watcher+Agent 단일 EXE)
3. `dps-store/docs/print/20260511-equipment-gui-spec.md` — GUI 공통 규칙·코드 샘플
4. `dps-store/docs/print/20260318-gtx4-module-design.md` — **본 모듈 메인 설계서** (GTX4CMD 연동, 다중 프린터, 플래튼/잉크 파라미터)
5. `dps-store/docs/print/20260402-garment-print-api.md` — 서버 API (Jarvis PDF, 자동 출력 큐)
6. `dps-store/docs/print/20260318-gtx4-source.md` — GTX4CMD.exe 커맨드라인 옵션 레퍼런스
7. `dps-store/docs/print/20260511-equipment-consistency-audit.md` — l/m 모듈 대비 본 모듈의 격차

추가로 참고:
- `dps-store/docs/print/20260310-printer-client-api.md` — 서버 측 클라이언트 API 전체 명세 (Device Auth, 큐 상태 전이)
- `dps-store/CLAUDE.md`의 "관련 외부 레포" 섹션

## 대외비 자료 인계 (필수)

본 모듈은 **Brother GTX-4 제조사 자료**를 사용한다.

- `.source/` 폴더의 `GTX4CMD.exe`, `GTX4Api.dll`, 샘플 PDF는 **git 미추적** (`.gitignore` 처리)
- **릴리즈 EXE에도 포함하지 않는다** (라이선스/유출 방지)
- 신규 담당자는 사내 채널로 별도 인계 받아 `.source/` 폴더에 직접 배치 필요
- `.history/` 도 동일하게 git 미추적 (IDE 작업 이력)

GTX4CMD 사용법은 `20260318-gtx4-source.md`(분석 결과)와 원본 PDF(`GTX4_Commandline_Ver.2.6.0_E.pdf`) 양쪽을 참조한다.

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
├── .source/                       # ❗대외비 (GTX4CMD.exe 등, git 미추적)
├── assets/fonts/                  # Pretendard 번들
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
├── work_order_builder.py          # 작업지시서 PDF 조립 (reportlab + qrcode + 한국어 CIDFont)
├── gtx4cmd.py                     # GTX4CMD.exe 래퍼
├── xml_builder.py                 # GTX4CMD XML 파라미터 빌드
├── build.bat                      # PyInstaller + --collect-all reportlab/qrcode 포함
├── requirements.txt               # reportlab, qrcode 추가
└── CLAUDE.md
```

### 두 종 출력 흐름 (2026-05-18~)

```
[GET /api/printer/garment] → jobs[]
  · garmentPending, workOrderPending (서버 sub status)
  · workOrder: { tenantName, brandName, printedBy, workUrl } (작업지시서 메타)

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
- `dps-store/app/api/printer/garment/*` 와 본 모듈의 `agent.py` / `api_client.py` 를 함께 본다
- API 인터페이스 변경 시 `dps-store/docs/print/20260402-garment-print-api.md` 동기 업데이트
