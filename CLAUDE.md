# CLAUDE.md - equip-sync-g-module (가먼트 프린터)

이 레포의 Claude 컨텍스트와 설계 문서는 **`dps-store`** 프로젝트에서 통합 관리한다.

- dps-store 로컬 경로: `~/Workspace/dps-store`
- 외부 레포 테이블·통합 정책: `dps-store/CLAUDE.md` 의 "관련 외부 레포" 섹션
- 관련 설계 문서: `dps-store/docs/print/*` (가먼트 모듈은 `20260318-gtx4-*.md`, `20260402-garment-print-api.md`, `20260511-equipment-gui-*.md`)

이 레포 단독 작업 시에도 위 문서를 우선 참조하라.

## 간단 정리 (메모)

- Brother GTX-4 가먼트 프린터 자동 출력 Windows 프로그램
- Watcher + Agent 통합 단일 exe (PyInstaller)
- 빌드 산출물: `equip-sync-g-vX.Y.Z.exe` (태그 push 시 GitHub Actions에서 자동 빌드)
- 출력 모드: `direct` (win32print) / `gtx4cmd` (GTX4CMD.exe 경유)
- `.source/` 폴더의 GTX4CMD.exe / GTX4Api.dll / PDF는 **대외비** (git 미추적, 릴리즈 비포함)
