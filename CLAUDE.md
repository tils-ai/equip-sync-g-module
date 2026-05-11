## 장비 연동 모듈 구현

### 프로젝트 개요

Brother GTX-4 가먼트 프린터와 연동하여 dps-store 서버의 디자인 PDF를 자동 출력하는 Windows 프로그램.

### 설계 문서

> 설계 문서는 **dps-store** 프로젝트에서 통합 관리합니다.
>
> - `dps-store/docs/print/20260318-gtx4-source.md` — GTX4CMD.exe 분석
> - `dps-store/docs/print/20260318-gtx4-module-design.md` — 모듈 설계 (Watcher, GTX4CMD GUI, Agent)
> - `dps-store/docs/print/20260402-garment-print-api.md` — 서버 API 설계

### 현재 상태

- Watcher 모듈 구현 완료 (폴더 감시 자동 출력)
- Agent 모듈 구현 완료 (dps-store API 풀링 → PDF 다운로드 → 출력 → 결과 보고)
- Device Auth 인증 구현 완료
- GitHub Actions 빌드 파이프라인 구성 완료

### 구조

```
equip-sync-g-module/
├── .source/               # GTX4CMD.exe, GTX4Api.dll (대외비, git 미추적)
├── .github/workflows/     # GitHub Actions 빌드
└── watcher/               # 프로그램 코드
    ├── main.py            # 진입점
    ├── gui.py             # CustomTkinter GUI (Watcher 탭 / Agent 탭)
    ├── config.py          # config.ini 관리
    ├── watcher.py         # 폴더 감시 (watchdog)
    ├── processor.py       # PDF 처리 (direct/gtx4cmd 분기)
    ├── printer.py         # win32print 직접 출력
    ├── gtx4cmd.py         # GTX4CMD.exe CLI 래퍼
    ├── xml_builder.py     # 인쇄 설정 XML 생성
    ├── agent.py           # API 풀링 루프 (adaptive 백오프)
    ├── api_client.py      # dps-store API 클라이언트
    ├── auth.py            # Device Auth 플로우
    ├── requirements.txt
    └── build.bat
```

### 출력 모드

- `direct`: win32print로 프린터 DC 직접 출력 (기본, 드라이버 설정 사용)
- `gtx4cmd`: GTX4CMD.exe 경유 (PNG → XML → ARX4 → 전송, 가먼트 전용 설정 동적 제어)

config.ini `[printer] mode` 또는 GUI 설정에서 전환 가능.

### 대외비 주의

- `.source/` 폴더의 exe, dll, PDF는 대외비 자료
- 릴리즈 빌드에도 exe/dll 미포함 → 현장 PC에서 경로 지정 방식
