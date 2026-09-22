"""가먼트 CLI 래퍼 - subprocess로 호출, 리턴 코드 해석.

legacy/pro 두 계열의 가먼트 CLI 를 auto-probe 로 선택한다(실제 벤더 도구는 빌드 시 중립명으로 복원됨).
API 라이브러리도 같은 방식으로 고른다 — 임베드본이 드라이버 세대와 안 맞으면(-1401 등)
그 PC 에 설치된 것으로 재시도한다. 배경은 `garment_runtime` 모듈 주석 참조.
"""

import csv
import datetime
import json
import logging
import os
import subprocess
import sys
import tempfile

import config
import garment_api
import garment_runtime

logger = logging.getLogger(__name__)

RETURN_CODES = {
    0: "성공",
    -1001: "드라이버 파일 없음 — 가먼트 프린터 드라이버 설치 확인",
    # -11xx 는 XML 요소 값 범위 초과 (가이드 3-1-3). 코드 번호만으로는 어느 설정이 문제인지
    # 알 수 없어 현장에서 원인을 못 찾는다. 요소명과 유효 범위를 함께 적는다.
    -1101: "출력 파일명과 같은 이름의 폴더가 CLI 폴더에 존재",
    -1102: "설정값 범위 초과: 매수(uiCopies)는 1~999",
    -1105: "설정값 범위 초과: 플래튼(byPlatenSize)은 0~4",
    -1106: "설정값 범위 초과: 잉크 조합(byInk)은 0~2",
    -1107: "설정값 범위 초과: 해상도(byResolution)",
    -1108: "설정값 범위 초과: 하이라이트(byHighlight)는 1~9",
    -1109: "설정값 범위 초과: 마스크(byMask)는 1~5",
    -1110: "설정값 범위 초과: 잉크량(byInkVolume)은 1~10",
    -1111: "설정값 범위 초과: 이중 인쇄(byDoublePrint)는 0~3",
    -1116: "설정값 범위 초과: 허용오차(byTolerance)는 0~50",
    -1117: "설정값 범위 초과: 최소 화이트(byMinWhite)는 1~6",
    -1118: "설정값 범위 초과: 초크(byChoke)는 0~10",
    -1120: "설정값 범위 초과: 채도(bySaturation)는 0~40",
    -1121: "설정값 범위 초과: 밝기(byBrightness)는 0~40",
    -1122: "설정값 범위 초과: 대비(byContrast)는 0~40",
    -1123: "설정값 범위 초과: 시안 밸런스(iCyanBalance)는 -5~5",
    -1124: "설정값 범위 초과: 마젠타 밸런스(iMagentaBalance)는 -5~5",
    -1125: "설정값 범위 초과: 옐로 밸런스(iYellowBalance)는 -5~5",
    -1133: "설정값 범위 초과: 블랙 밸런스(iBlackBalance)는 -5~5",
    -1135: "설정값 범위 초과: 일시정지 간격(byPauseSpan)은 0~60",
    -1137: "설정값 범위 초과: 분할 간격(byDivideSpan)은 0~60",
    -1401: "드라이버 파일 없음 — 가먼트 프린터 드라이버/API 라이브러리 위치 확인",
    -1402: "메모리 할당 실패",
    -1403: "프린터를 찾을 수 없거나 드라이버 사용 불가",
    -1404: "드라이버로 인쇄 시작 실패",
    -1405: "드라이버로 인쇄 시작 실패",
    -1406: "작업 파일 생성 실패",
    -1701: "드라이버 파일 없음 — API 라이브러리가 드라이버측 모듈을 찾지 못함",
    -1705: "메모리 할당 실패",
    -1706: "디바이스 컨텍스트 획득 실패",
    -1707: "이미지 데이터 획득 실패",
    -2001: "PNG 파일이 아니거나 로드 불가",
    -2002: "이미지 파일 로드 실패",
    -2003: "투명 레이어 분리 실패",
    -2004: "RGB(255,255,255) → 화이트 변환 실패",
    -2401: "프린터 미발견 또는 LAN 미연결",
    -2701: "프린터 연결 실패",
    -3102: "XML 파일 없음",
    -3103: "이미지 파일 없음",
    -3104: "-P와 -A 동시 지정 불가",
    -3108: "-S 와 -R 동시 지정 불가 또는 둘 다 미지정",
}

# 파일/DLL 누락·드라이버 로드 실패 계열 — 발생 시 별도 진단 .txt 파일을 생성한다.
_FILE_MISSING_CODES = {-1001, -1401, -1403, -2001, -3102, -3103}

# 설정값 범위 초과 계열 — 어느 값이 문제인지 보려면 XML 을 봐야 하므로 함께 진단서를 남긴다.
_VALUE_RANGE_CODES = {
    -1101, -1102, -1105, -1106, -1107, -1108, -1109, -1110, -1111,
    -1116, -1117, -1118, -1120, -1121, -1122, -1123, -1124, -1125,
    -1133, -1135, -1137,
}

# 진단 보고서를 남길 코드 전체.
_REPORT_CODES = _FILE_MISSING_CODES | _VALUE_RANGE_CODES

# `--windowed` 로 빌드한 EXE 에서 자식 프로세스를 그냥 띄우면 콘솔 창이 깜빡인다.
# 진단서를 쓸 때마다 PowerShell 창이 서너 개 떴다 꺼지던 원인이다. 창 없이 실행한다.
# (`printer.py` 의 poppler 호출이 같은 이유로 이미 이렇게 돌고 있다)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 드라이버/장비 매칭 실패 계열 — "이 CLI 가 이 장비에 안 맞음" 신호.
# 이 코드일 때만 다른 계열(legacy ↔ pro)의 가먼트 CLI 로 fallback 한다.
# (-2001/-3102/-3103 같은 입력 오류는 다른 CLI 로도 동일 실패하므로 제외)
_DRIVER_MISMATCH_CODES = {-1001, -1401, -1403, -1701}

# auto-probe 로 확정된 가먼트 CLI exe 경로 (프로세스 메모리 캐시).
_active_exe: str | None = None

# auto-probe 로 확정된 API 라이브러리 경로 (프로세스 메모리 캐시).
# "" = 임베드본 확정, None = 아직 미확정.
_active_api: str | None = None

# 세대 불일치 안내를 프로세스당 1회만 남기기 위한 플래그.
_mismatch_logged = False


def _model_for_exe(exe: str) -> str:
    base = os.path.basename(exe or "").lower()
    if "pro" in base:
        return "pro"
    if "legacy" in base:
        return "legacy"
    return ""


def _exe_for_model(model: str) -> str:
    return {"legacy": config.LEGACY_CLI_EXE, "pro": config.PRO_CLI_EXE}.get(model, "")


def _printer_driver_name(printer_name: str = "") -> str:
    """Windows 프린터 큐의 DriverName. 조회 실패 시 빈 문자열."""
    if not printer_name:
        return ""
    try:
        import win32print

        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
        finally:
            win32print.ClosePrinter(handle)
    except Exception:
        return ""
    return info.get("pDriverName") or ""


def _preferred_model_for_printer(printer_name: str = "") -> str:
    """설정값과 Windows 드라이버명으로 대상 CLI 계열을 판정한다."""
    forced = getattr(config, "GTX_CLI", "auto")
    if forced in ("pro", "legacy"):
        return forced

    driver = _printer_driver_name(printer_name)
    target = f"{driver} {printer_name or ''}".lower()
    if "gtx pro" in target or "gtxpro" in target:
        return "pro"
    if "gtx-4" in target or "gtx4" in target:
        return "legacy"
    return ""


def preferred_data_extension(printer_name: str = "") -> str:
    """현재 대상 계열에 맞는 가먼트 인쇄 데이터 확장자 반환.

    GTX pro CMD는 ARXP 포맷을 생성/전송하므로 .arxp를 사용한다. 아직
    active CLI가 확정되기 전에는 프린터명으로 GTX pro 장비를 보수적으로
    판정한다.
    """
    if _preferred_model_for_printer(printer_name) == "pro":
        return ".arxp"
    active = _load_active_exe()
    if _model_for_exe(active or "") == "pro":
        return ".arxp"
    return ".arx4"


def _load_active_exe() -> str | None:
    """확정된 CLI 를 메모리→상태파일 순으로 조회. 유효한 exe 경로면 반환."""
    global _active_exe
    if _active_exe and os.path.isfile(_active_exe):
        return _active_exe
    try:
        with open(config.ACTIVE_CMD_STATE, encoding="utf-8") as f:
            exe = _exe_for_model(f.read().strip())
        if exe and os.path.isfile(exe):
            _active_exe = exe
            return exe
    except OSError:
        pass
    return None


def _save_active_exe(exe: str) -> None:
    global _active_exe
    _active_exe = exe
    try:
        with open(config.ACTIVE_CMD_STATE, "w", encoding="utf-8") as f:
            f.write(_model_for_exe(exe))
    except OSError:
        logger.warning("active 가먼트 CLI 상태 저장 실패: %s", config.ACTIVE_CMD_STATE)


def _clear_active_exe() -> None:
    """확정 CLI 캐시 폐기 → 다음 create 작업에서 재probe."""
    global _active_exe
    _active_exe = None
    try:
        os.remove(config.ACTIVE_CMD_STATE)
    except OSError:
        pass


def _load_active_api() -> str | None:
    """확정된 API 라이브러리 경로. "" = 임베드본, None = 미확정."""
    global _active_api
    if _active_api is not None:
        if _active_api == "" or os.path.isfile(_active_api):
            return _active_api
        _active_api = None
    try:
        with open(config.ACTIVE_API_STATE, encoding="utf-8") as f:
            saved = f.read().strip()
    except OSError:
        return None
    if saved and not os.path.isfile(saved):
        return None  # 설치본이 사라짐(드라이버 재설치 등) → 재probe
    _active_api = saved
    return saved


def _save_active_api(api_dll: str) -> None:
    global _active_api
    _active_api = api_dll
    try:
        with open(config.ACTIVE_API_STATE, "w", encoding="utf-8") as f:
            f.write(api_dll)
    except OSError:
        logger.warning("active 가먼트 API 상태 저장 실패: %s", config.ACTIVE_API_STATE)


def _clear_active_api() -> None:
    global _active_api
    _active_api = None
    try:
        os.remove(config.ACTIVE_API_STATE)
    except OSError:
        pass


def _candidate_apis(exe: str) -> list:
    """이 exe 로 시도할 API 라이브러리 목록. "" = 임베드본(복사 없이 그대로 실행).

    기본 auto 는 **설치본 먼저**다. 설치본은 그 PC 의 드라이버와 한 패키지로 깔린 것이라
    세대가 맞고, 임베드본은 우리가 확보한 시점에 굳은 것이라 안 맞을 수 있다. 처음에는
    임베드본을 먼저 뒀는데, 현장에서 매 작업마다 -1401 로 한 번 실패한 뒤에야 설치본으로
    넘어가는 낭비가 드러났다(진단서 생성까지 따라붙어 7초). 순서를 뒤집는다.

    설치본이 없거나 그것도 드라이버를 못 찾으면 임베드본으로 내려간다.
    """
    mode = getattr(config, "GARMENT_API_DLL", "auto") or "auto"
    if mode not in ("auto", "embedded", "installed"):
        return [mode] if os.path.isfile(mode) else [""]
    if mode == "embedded":
        return [""]

    cached = _load_active_api()
    if cached is not None:
        # 확정본도 세대 검사를 통과해야 한다. 세대 판정이 생기기 전에 확정된 것이 파일로 남아
        # 있으면, 버전을 올려도 그 조합을 계속 쓰게 된다(현장에서 실제로 그랬다).
        if cached == "" or mode != "auto" or _same_generation(exe, cached):
            return [cached]
        logger.warning(
            "확정돼 있던 API 가 CLI 와 세대가 달라 폐기합니다: %s",
            garment_runtime.describe_file(cached),
        )
        _clear_active_api()

    embedded = garment_runtime.api_dll_for(exe)
    installed = garment_runtime.installed_api_dlls(embedded)
    if mode == "installed":
        # 운영자가 직접 고른 경우 — 세대가 달라도 시도한다. 대신 경고는 남긴다.
        for path in installed:
            if not _same_generation(exe, path):
                logger.warning(
                    "설정이 설치본 고정이라 세대가 다른 라이브러리를 씁니다: %s",
                    garment_runtime.describe_file(path),
                )
        return installed or [""]
    return _same_generation_only(exe, installed) + [""]


def _same_generation(exe: str, api_dll: str) -> bool:
    """CLI 와 API 라이브러리가 같은 세대(major)인지."""
    cli_major = garment_runtime.major_version(exe)
    api_major = garment_runtime.major_version(api_dll)
    return bool(cli_major) and cli_major == api_major


def _same_generation_only(exe: str, installed: list) -> list:
    """설치본 중 CLI 와 세대가 같은 것만. 세대가 다른 것은 쓰지 않고 경고한다.

    세대가 다르면 인쇄 설정 구조가 어긋난다. 5.x 는 4.x 대비 항목이 중간에 하나 늘어(winkver)
    그 뒤 값이 전부 한 칸씩 밀린다. 값 검증에 걸리면 그나마 다행이고, 안 걸리면 **플래튼·잉크
    같은 값이 엉뚱하게 적용된 채 출력된다.** 옷을 버리는 쪽이 훨씬 비싸므로 섞지 않는다.
    """
    global _mismatch_logged
    usable, mismatched = [], []
    for path in installed:
        (usable if _same_generation(exe, path) else mismatched).append(path)
    # 임베드본이 드라이버와 맞는 PC 에서도 이 경로를 지난다. 매 작업마다 빨간 줄을 쌓으면
    # 정상 동작을 장애로 오해하게 되므로, 프로세스당 한 번만 경고로 알린다.
    if mismatched and not usable and not _mismatch_logged:
        _mismatch_logged = True
        logger.warning(
            "설치된 API 라이브러리는 CLI 와 세대가 달라 쓰지 않습니다 — 임베드본으로 진행합니다."
        )
        logger.warning("  CLI  : %s", garment_runtime.describe_file(exe))
        for path in mismatched:
            logger.warning("  설치본: %s", garment_runtime.describe_file(path))
        logger.warning(
            "  임베드본으로도 드라이버를 못 찾으면(-1401) 이 PC 드라이버 세대에 맞는 CLI 가 "
            "필요합니다. 설정의 'API 라이브러리'를 '설치본 고정'으로 두면 세대를 무시하고 씁니다."
        )
    return usable


def _candidate_exes(printer_name: str = "") -> list:
    """probe 후보 — 프린터 계열이 명확하면 해당 CLI만 사용한다."""
    preferred = _preferred_model_for_printer(printer_name)
    if preferred:
        exe = _exe_for_model(preferred)
        return [exe] if exe and os.path.isfile(exe) else []

    out = []
    for exe in (_load_active_exe(), config.LEGACY_CLI_EXE, config.PRO_CLI_EXE):
        if exe and os.path.isfile(exe) and exe not in out:
            out.append(exe)
    return out


def describe_cli_selection(printer_name: str = "") -> str:
    """Return the GTX CLI mode currently selected for logging."""
    active = _load_active_exe()
    preferred = _preferred_model_for_printer(printer_name)
    candidates = _candidate_exes(printer_name)
    active_label = _model_for_exe(active) if active else "auto"
    candidate_labels = [
        f"{_model_for_exe(exe) or 'unknown'}:{os.path.basename(exe)}"
        for exe in candidates
    ]
    return (
        f"garment_mode={config.GARMENT_MODE}, "
        f"gtx_cli={active_label}, "
        f"gtx_cli_setting={getattr(config, 'GTX_CLI', 'auto')}, "
        f"preferred={preferred or 'auto'}, "
        f"candidates={', '.join(candidate_labels) or '(none)'}"
    )


def describe_versions(printer_name: str = "") -> str:
    """현재 조합의 버전 요약 — CLI · API 라이브러리 · 드라이버측 파일."""
    exe = (
        _load_active_exe()
        or _exe_for_model(_preferred_model_for_printer(printer_name))
        or config.PRO_CLI_EXE
        or config.LEGACY_CLI_EXE
    )
    if not exe or not os.path.isfile(exe):
        return "(가먼트 CLI 없음)"
    return garment_runtime.version_summary(exe, _load_active_api() or "")


def printer_driver_summary(printer_name: str | None) -> str:
    """Return the Windows printer queue/driver used by this job."""
    if not printer_name:
        return "printer=(none), driver=(unknown)"
    try:
        import win32print

        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        return f"printer={printer_name}, driver=(lookup failed: {e})"

    driver = info.get("pDriverName") or "(unknown)"
    port = info.get("pPortName") or "(unknown)"
    status = info.get("Status")
    return f"printer={printer_name}, driver={driver}, port={port}, status={status}"


def _extract_arg_path(args: list, flag: str) -> str | None:
    """args 에서 `flag` 다음 위치의 값(경로)을 반환. 없으면 None."""
    try:
        i = args.index(flag)
    except ValueError:
        return None
    return args[i + 1] if i + 1 < len(args) else None


def _normalize_returncode(rc: int) -> int:
    """Windows subprocess 가 음수 종료 코드를 unsigned 32-bit 로 주는 케이스 정규화."""
    if rc > 0x7FFFFFFF:
        rc -= 0x100000000
    return rc


def _run(args: list, exe: str = None, printer_name: str = None,
         api_dll: str = None) -> int:
    """가먼트 CLI 실행, 리턴 코드 반환.

    exe 미지정 시 auto-probe 로 확정된 CLI → legacy 계열 순으로 사용한다.
    (send/status/제어 등은 exe 를 넘기지 않으므로 자동으로 확정 CLI 를 재사용)

    api_dll 미지정 시 확정된 API 라이브러리를 재사용한다. 값이 있으면(설치본) CLI 와
    그 라이브러리만 담은 실행 폴더를 만들어 거기서 돌린다 — Windows 는 exe 폴더의
    DLL 을 먼저 집으므로, 이것이 어떤 라이브러리가 쓰일지 확정하는 유일한 방법이다.
    """
    if api_dll is None:
        api_dll = _load_active_api() or ""
    if exe is None:
        preferred = _preferred_model_for_printer(printer_name or "")
        preferred_exe = _exe_for_model(preferred)
        exe = (
            preferred_exe
            if preferred_exe and os.path.isfile(preferred_exe)
            else (_load_active_exe() or config.LEGACY_CLI_EXE)
        )
    if not exe:
        raise FileNotFoundError(
            "가먼트 CLI 경로가 설정되지 않았습니다. "
            "config.ini [garment_cli] cli_legacy_path / cli_pro_path 또는 .source 폴더를 확인하세요."
        )
    run_exe = garment_runtime.prepare(exe, api_dll) if api_dll else exe
    cmd = [run_exe] + args
    # CLI exe 와 동봉 DLL/드라이버 자료가 같은 폴더에 있어야 정상 동작.
    # cwd 를 exe 폴더로 강제해 Graphiclabs 와 동일한 실행 컨텍스트 보장.
    cwd = os.path.dirname(run_exe) or None
    logger.debug("실행 (cwd=%s): %s", cwd, " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, timeout=120, cwd=cwd,
        stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
    )
    rc = _normalize_returncode(result.returncode)
    if rc != 0:
        desc = RETURN_CODES.get(rc, f"알 수 없는 에러 ({rc})")
        logger.error("가먼트 CLI 에러 (rc=%d): %s", rc, desc)
        stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        if stdout:
            logger.error("가먼트 CLI stdout: %s", stdout)
        if stderr:
            logger.error("가먼트 CLI stderr: %s", stderr)
        if rc in _REPORT_CODES:
            try:
                report_path = _write_diagnostic_report(
                    run_exe, cwd, args, rc, result.stdout, result.stderr,
                    printer_name=printer_name,
                )
                logger.error("진단 보고서 저장됨: %s", report_path)
            except Exception:
                logger.exception("진단 보고서 저장 실패")
        # 확정(active) CLI 가 드라이버/장비 매칭 실패를 내면 캐시 폐기 → 다음 작업에서 재probe
        if rc in _DRIVER_MISMATCH_CODES and exe == _active_exe:
            logger.warning(
                "확정 가먼트 CLI(%s) 매칭 실패(rc=%d) → 캐시 폐기, 다음 작업에서 재탐색",
                os.path.basename(exe), rc,
            )
            _clear_active_exe()
        # API 라이브러리도 같은 신호로 재탐색 대상이다 (드라이버를 올린 직후 등).
        if rc in _DRIVER_MISMATCH_CODES and api_dll == _active_api:
            logger.warning(
                "확정 가먼트 API(%s) 매칭 실패(rc=%d) → 캐시 폐기, 다음 작업에서 재탐색",
                os.path.basename(api_dll) if api_dll else "임베드본", rc,
            )
            _clear_active_api()
    return rc


# ------------------------------------------------------------------------------
# 진단 보고서 — 파일/DLL 누락·드라이버 로드 실패 시 환경 점검 결과를 .txt 로 저장.
# 메인 watcher.log 가 비대해지지 않도록 사건당 1개 파일을 시간 기준으로 생성한다.
# ------------------------------------------------------------------------------

def _format_dir_listing(dir_path: str, indent: str = "  ") -> list[str]:
    """디렉토리 항목 listing 을 라인 리스트로 반환 (보고서용)."""
    if not dir_path:
        return [f"{indent}(경로 없음)"]
    if not os.path.isdir(dir_path):
        return [f"{indent}{dir_path} — 폴더가 존재하지 않음"]
    try:
        entries = sorted(os.listdir(dir_path))
    except OSError as e:
        return [f"{indent}{dir_path} — 목록 조회 실패: {e}"]
    lines = [f"{indent}{dir_path} (항목 {len(entries)}개)"]
    for name in entries:
        full = os.path.join(dir_path, name)
        if os.path.isdir(full):
            lines.append(f"{indent}  [D] {name}")
        else:
            try:
                size = os.path.getsize(full)
                lines.append(f"{indent}  [F] {name} ({size:,} bytes)")
            except OSError:
                lines.append(f"{indent}  [F] {name} (크기 조회 실패)")
    return lines


def _check_zone_identifier(path: str) -> str:
    """NTFS ADS Zone.Identifier 존재 = Windows '다른 컴퓨터에서 받음' 차단 표시."""
    if not os.path.isfile(path):
        return "(파일 없음)"
    ads = path + ":Zone.Identifier"
    try:
        with open(ads, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
    except FileNotFoundError:
        return "정상 (차단 표시 없음)"
    except OSError as e:
        return f"확인 실패: {e}"
    if not content:
        return "차단 표시 있음 (Zone 정보 비어있음)"
    return "차단됨 — " + content.replace("\r", "").replace("\n", " | ")


def _check_architecture(path: str) -> str:
    """PE 헤더 IMAGE_FILE_MACHINE → 아키텍처 문자열.

    관리(.NET) 실행파일은 machine 이 x86 으로 찍혀도 AnyCPU 면 64비트로 뜬다.
    machine 만 보고 "32-bit" 라고 적으면 64비트 라이브러리와 짝이 안 맞는 것처럼 보여
    엉뚱한 곳을 파게 된다(실제로 그랬다). CLR 헤더 플래그까지 봐야 한다.
    """
    if not os.path.isfile(path):
        return "(파일 없음)"
    machine, cor_flags = garment_runtime.pe_machine_and_corflags(path)
    if machine is None:
        return "PE 아님 또는 헤더 읽기 실패"
    label = {
        0x014C: "x86 (32-bit)",
        0x8664: "x64 (64-bit)",
        0xAA64: "ARM64",
    }.get(machine, f"알 수 없음 (machine=0x{machine:04X})")
    if cor_flags is None:
        return label
    if cor_flags & 0x2:
        return "x86 (32-bit) — .NET 32BITREQUIRED"
    if cor_flags & 0x20000:
        return "x86 우선 — .NET 32BITPREFERRED (64비트 OS 에서도 32비트로 실행)"
    return ".NET AnyCPU (64비트 OS 에서 64비트로 실행 — machine 값은 x86 으로 표기됨)"


def _check_vcruntime() -> list[tuple[str, bool]]:
    """VC++ 재배포 런타임 DLL 존재 여부 — 가먼트 API DLL 이 의존."""
    sys32 = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32")
    needed = [
        "vcruntime140.dll", "vcruntime140_1.dll",
        "msvcp140.dll", "msvcp140_1.dll",
    ]
    return [(n, os.path.isfile(os.path.join(sys32, n))) for n in needed]


def _ps(script: str, timeout: int = 15) -> str:
    """PowerShell 일회성 실행 결과를 텍스트로 반환. 실패 시 사유 문자열 반환."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=timeout,
            stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        return "(PowerShell 미발견)"
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(실행 실패: {e})"
    out = result.stdout.decode("utf-8", errors="replace").strip()
    err = result.stderr.decode("utf-8", errors="replace").strip()
    if not out and err:
        return f"(stderr) {err}"
    return out or "(출력 없음)"


def _diagnostic_dir() -> str:
    """진단 텍스트 파일 저장 폴더 — <watcher.log 폴더>/diagnostics."""
    log_dir = os.path.dirname(config.LOG_FILE) or os.path.join(config.BASE_DIR, "logs")
    diag_dir = os.path.join(log_dir, "diagnostics")
    os.makedirs(diag_dir, exist_ok=True)
    return diag_dir


def _write_diagnostic_report(exe: str, cwd: str | None, args: list, rc: int,
                              stdout: bytes, stderr: bytes,
                              printer_name: str = None) -> str:
    """진단 보고서 텍스트 파일 작성, 저장 경로 반환.

    파일명: garment_cli-YYYYMMDD-HHMMSS-rc{|rc|}.txt
    """
    now = datetime.datetime.now()
    fname = f"garment_cli-{now.strftime('%Y%m%d-%H%M%S')}-rc{abs(rc)}.txt"
    path = os.path.join(_diagnostic_dir(), fname)

    desc = RETURN_CODES.get(rc, f"알 수 없는 에러 ({rc})")
    exe_dir = os.path.dirname(exe) if exe else (cwd or "")
    target_printer = printer_name or _extract_arg_path(args, "-P") or config.PRINTER_NAME
    # DLL 원본명을 코드에 박지 않고 exe 폴더의 .dll 을 동적 점검한다.
    try:
        dll_paths = (
            [os.path.join(exe_dir, f) for f in sorted(os.listdir(exe_dir)) if f.lower().endswith(".dll")]
            if exe_dir and os.path.isdir(exe_dir)
            else []
        )
    except OSError:
        dll_paths = []

    L: list[str] = []
    L.append("=" * 70)
    L.append("가먼트 CLI 진단 보고서")
    L.append(f"시각      : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"종료 코드 : {rc}  ({desc})")
    L.append("=" * 70)

    L.append("")
    L.append("[1] 실행 정보")
    L.append(f"  CLI exe 경로 : {exe}")
    L.append(f"  실행 cwd     : {cwd or '(미지정)'}")
    L.append(f"  전달 args    : {' '.join(args)}")
    L.append(f"  GTX mode     : {describe_cli_selection(target_printer)}")
    L.append(f"  Printer info : {printer_driver_summary(target_printer)}")
    L.append(f"  버전 조합    : {describe_versions(target_printer)}")
    L.append(f"  API 선택     : {getattr(config, 'GARMENT_API_DLL', 'auto')}")
    L.append(f"  출력 경로    : {getattr(config, 'GARMENT_BACKEND', 'cli')}")
    L.append(f"  실행 빌드    : {getattr(config, 'APP_VERSION', '?')}")

    L.append("")
    L.append("[2] CLI exe / API DLL 점검")
    targets = [("CLI exe", exe)] + [(os.path.basename(d), d) for d in dll_paths]
    for label, p in targets:
        L.append(f"  -- {label} --")
        L.append(f"    경로           : {p or '(경로 없음)'}")
        if not p:
            continue
        exists = os.path.isfile(p)
        L.append(f"    존재           : {exists}")
        if exists:
            try:
                L.append(f"    크기           : {os.path.getsize(p):,} bytes")
            except OSError:
                L.append("    크기           : (조회 실패)")
            L.append(f"    Windows 차단   : {_check_zone_identifier(p)}")
            L.append(f"    아키텍처       : {_check_architecture(p)}")

    L.append("")
    L.append("[3] CLI 폴더 listing")
    L.extend(_format_dir_listing(exe_dir))

    # 입력 파일 누락 계열 — 해당 파일의 상위 폴더도 점검.
    if rc in (-2001, -3103):
        img = _extract_arg_path(args, "-I")
        if img:
            L.append("")
            L.append("[3b] 입력 이미지")
            L.append(f"  경로 : {img}")
            L.append(f"  존재 : {os.path.isfile(img)}")
            L.append("  상위 폴더:")
            L.extend(_format_dir_listing(os.path.dirname(img), indent="    "))
    if rc == -3102:
        xml = _extract_arg_path(args, "-X")
        if xml:
            L.append("")
            L.append("[3b] 입력 XML")
            L.append(f"  경로 : {xml}")
            L.append(f"  존재 : {os.path.isfile(xml)}")
            L.append("  상위 폴더:")
            L.extend(_format_dir_listing(os.path.dirname(xml), indent="    "))

    # 설정값 범위 초과(-11xx)는 넘긴 XML 안에 답이 있다. 로그만 보고 추리하지 않도록 싣는다.
    xml_arg = _extract_arg_path(args, "-X")
    if xml_arg:
        L.append("")
        L.append("[3c] 인쇄 설정 XML")
        L.append(f"  경로 : {xml_arg}")
        try:
            with open(xml_arg, encoding="utf-8") as f:
                for line in f.read().splitlines():
                    L.append(f"    {line}")
        except OSError as e:
            L.append(f"  읽기 실패: {e}")

    L.append("")
    L.append("[4] VC++ 재배포 런타임 (System32) — 가먼트 API DLL 의존 모듈")
    for name, ok in _check_vcruntime():
        L.append(f"  {name:<25} : {'존재' if ok else '없음 (재배포 패키지 미설치 가능성)'}")

    L.append("")
    L.append("[5] Print Spooler 서비스")
    L.append(_ps(
        "(Get-Service Spooler | Select-Object Status,Name,StartType,DisplayName "
        "| Format-List | Out-String).Trim()"
    ))

    L.append("")
    L.append("[6] Brother 프린터 드라이버 (Get-PrinterDriver)")
    L.append(_ps(
        "$d = Get-PrinterDriver | Where-Object { $_.Name -match 'GTX|Brother' }; "
        "if ($d) { ($d | Select-Object Name,Manufacturer,DriverVersion,MajorVersion,"
        "ConfigFile,DataFile,DriverPath,InfPath | "
        "Format-List | Out-String).Trim() } else { '가먼트 프린터 드라이버 없음 — "
        "벤더 공식 설치 프로그램으로 가먼트 프린터 드라이버 설치 필요' }"
    ))

    L.append("")
    L.append("[7] Brother 프린터 큐 (Get-Printer)")
    L.append(_ps(
        "$p = Get-Printer | Where-Object { $_.Name -match 'GTX|Brother' }; "
        "if ($p) { ($p | Select-Object Name,DriverName,PortName,PrinterStatus | "
        "Format-List | Out-String).Trim() } else { 'Brother/GTX 프린터 없음' }"
    ))

    L.append("")
    L.append("[7b] 드라이버측 처리 모듈 / API 라이브러리 후보")
    L.append("  API 라이브러리는 아래 드라이버측 모듈을 찾아 로드한다. -1401 은 그 탐색 실패다.")
    used_api = garment_runtime.api_dll_for(exe)
    origin_exe = _exe_for_model(_model_for_exe(exe)) or exe
    embedded_api = garment_runtime.api_dll_for(origin_exe)
    L.append(f"  이번 실행 API: {garment_runtime.describe_file(used_api)}")
    L.append(f"  임베드 API   : {garment_runtime.describe_file(embedded_api)}")
    active_api = _load_active_api()
    L.append(
        "  확정 API     : "
        + ("(미확정)" if active_api is None else
           garment_runtime.describe_file(active_api) if active_api else "임베드본")
    )
    L.append(f"  스풀 드라이버 폴더: {garment_runtime.spool_driver_dir()}")
    driver_modules = garment_runtime.driver_files(garment_runtime.driver_file_prefix(embedded_api))
    if driver_modules:
        for line in driver_modules:
            L.append(f"    {line}")
    else:
        L.append("    (해당 계열 드라이버 파일 없음 — 드라이버 미설치 또는 다른 계열)")
    installed = garment_runtime.installed_api_dlls(embedded_api)
    L.append(f"  설치된 동일 이름 라이브러리 {len(installed)}개")
    for installed_path in installed:  # `path`(보고서 저장 경로)를 가리지 않도록 별도 이름
        L.append(f"    {garment_runtime.describe_file(installed_path)}")

    L.append("")
    L.append("[8] 가먼트 CLI 표준 출력")
    so = (stdout or b"").decode("utf-8", errors="replace").strip()
    se = (stderr or b"").decode("utf-8", errors="replace").strip()
    L.append(f"  stdout : {so or '(없음)'}")
    L.append(f"  stderr : {se or '(없음)'}")

    L.append("")
    L.append("=" * 70)
    L.append("끝")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def _run_with_probe(args: list, printer_name: str = None) -> int:
    """ARX4 생성(print) 전용 — 후보 CLI 를 순회하며 성공하는 것을 확정·캐싱한다.

    - 성공(rc==0): 해당 CLI 를 확정(메모리+상태파일)하고 0 반환.
    - 드라이버/장비 매칭 실패(_DRIVER_MISMATCH_CODES): 다음 후보로 fallback.
    - 그 외 실패(입력 오류 등): 다른 CLI 로도 동일 실패하므로 즉시 반환.
    - 모든 후보 실패: 캐시 폐기 후 마지막 rc 반환.

    print(-A) 는 실제 장비로 전송하지 않지만, 계열이 다른 CLI가 성공하면
    잘못된 포맷 파일을 만들 수 있다. 프린터명으로 계열이 확정되면 해당 CLI만 사용한다.
    여기서 확정된 CLI 를 send/status/제어가 재사용한다.
    """
    candidates = _candidate_exes(printer_name)
    if not candidates:
        return _run(args, printer_name=printer_name)  # 설정 없음 → 기존 경로(FileNotFoundError) 위임
    last_rc = None
    for exe in candidates:
        for api_dll in _candidate_apis(exe):
            rc = _run(args, exe=exe, printer_name=printer_name, api_dll=api_dll)
            if rc == 0:
                if exe != _active_exe:
                    _save_active_exe(exe)
                    logger.info("가먼트 CLI 확정: %s", os.path.basename(exe))
                if api_dll != _active_api:
                    _save_active_api(api_dll)
                    logger.info("가먼트 API 확정: %s", garment_runtime.describe_file(api_dll)
                                if api_dll else "임베드본")
                return 0
            if rc not in _DRIVER_MISMATCH_CODES:
                # 여기까지 왔다는 것은 드라이버 매칭은 통과했다는 뜻이다(값 오류 등 다른 실패).
                # 조합을 확정해 두지 않으면 다음 작업도 실패하는 조합부터 다시 훑어
                # 매번 -1401 과 진단서를 반복한다.
                if exe != _active_exe:
                    _save_active_exe(exe)
                if api_dll != _active_api:
                    _save_active_api(api_dll)
                    logger.info(
                        "가먼트 API 확정(드라이버 매칭 통과): %s",
                        garment_runtime.describe_file(api_dll) if api_dll else "임베드본",
                    )
                return rc  # 입력 오류 등 — fallback 무의미
            last_rc = rc
    logger.error("모든 가먼트 CLI/API 조합 매칭 실패 (마지막 rc=%s)", last_rc)
    _clear_active_exe()
    _clear_active_api()
    return last_rc if last_rc is not None else -1401


def api_backend_active(printer_name: str = "") -> bool:
    """호출자(processor)가 백엔드를 물을 때 쓰는 공개 이름."""
    return _api_backend_active(printer_name)


def _api_backend_active(printer_name: str = "") -> bool:
    """이번 작업을 라이브러리 직접 호출로 처리할지.

    auto 는 **세대가 맞는 CLI 조합이 없을 때만** 직접 호출로 넘어간다. CLI 로 되는 현장의
    동작은 그대로 두고, CLI 가 못 쓰는 현장만 구제하기 위해서다.
    """
    backend = getattr(config, "GARMENT_BACKEND", "cli")
    if backend == "api":
        return True
    if backend != "auto":
        return False
    exe = _exe_for_model(_preferred_model_for_printer(printer_name)) or config.PRO_CLI_EXE
    if not exe or not os.path.isfile(exe):
        return False
    embedded = garment_runtime.api_dll_for(exe)
    installed = garment_runtime.installed_api_dlls(embedded)
    # 임베드본이 드라이버와 맞으면 CLI 로 충분하다. 설치본만 있고 세대가 다르면 CLI 가 못 쓴다.
    return bool(installed) and not any(_same_generation(exe, p) for p in installed)


def _last_direct_trace(tail: int = 12) -> list:
    """직접 호출 기록 파일의 마지막 줄들 — 자식이 죽어 표준 출력을 잃었을 때 쓴다."""
    log_dir = os.path.dirname(config.LOG_FILE) or os.path.join(config.BASE_DIR, "logs")
    diag = os.path.join(log_dir, "diagnostics")
    try:
        files = [f for f in os.listdir(diag) if f.startswith("api-direct-")]
        newest = max(files, key=lambda f: os.path.getmtime(os.path.join(diag, f)))
    except (OSError, ValueError):
        return ["  (직접 호출 기록 파일 없음)"]
    path = os.path.join(diag, newest)
    try:
        with open(path, encoding="utf-8") as f:
            body = f.read().splitlines()
    except OSError:
        return [f"  (기록 파일 읽기 실패: {path})"]
    out = [f"  마지막 기록: {path}"]
    out.extend(f"  | {line}" for line in body[-tail:])
    out.append("  | ↑ 여기까지 진행하고 죽었습니다")
    return out


def _make_arxp_isolated(image_path: str, out_path: str, model: str,
                        position: str, size: str, overrides: dict) -> tuple:
    """인쇄 데이터 생성을 **자식 프로세스**에서 돌린다.

    벤더 라이브러리에서 접근 위반이 나면 파이썬 예외로 잡히지 않고 프로세스가 그대로 죽는다.
    한 몸으로 돌리면 GUI 까지 같이 내려간다(현장에서 출력 버튼을 누르는 순간 앱이 꺼졌다).
    자식으로 떼어 두면 최악이라도 그 작업만 실패하고 앱은 살아 있는다.

    배포본이 아닐 때(개발 실행)는 자식으로 뜰 대상이 없으므로 같은 프로세스에서 돈다.
    """
    if not getattr(sys, "frozen", False):
        return garment_api.make_arxp(
            image_path, out_path, model=model, position=position, size=size, overrides=overrides
        )

    cmd = [sys.executable, "--api-makearxp", image_path, out_path,
           "--model", model, "--position", position, "--size", size,
           "--opt", json.dumps(overrides or {})]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=180,
            stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return None, ["  직접 호출 자식 프로세스 시간 초과(180초)"]

    text = (result.stdout or b"").decode("utf-8", "replace")
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("RC=")]
    rc = None
    for line in text.splitlines():
        if line.startswith("RC="):
            try:
                rc = int(line[3:].strip())
            except ValueError:
                rc = None
    if rc is None:
        code = _normalize_returncode(result.returncode)
        lines.append(f"  자식 프로세스가 결과를 남기지 못하고 종료했습니다 (exit={code})")
        lines.append("  → 라이브러리 호출에서 프로세스가 죽은 것으로 봅니다. 앱은 계속 동작합니다.")
        lines.extend(_last_direct_trace())
        err = (result.stderr or b"").decode("utf-8", "replace").strip()
        if err:
            lines.append(f"  stderr: {err[:500]}")
    return rc, lines


def create_arx4(xml_path: str, image_path: str, arx4_path: str,
                position: str = None, size: str = None,
                magnification: str = None, white: int = None,
                printer_name: str = None, option_overrides: dict = None) -> int:
    """PNG + XML → 인쇄 데이터 생성.

    백엔드가 직접 호출이면 XML 없이 구조체로 바로 만든다. 그 경우 `xml_path` 는 쓰이지 않는다.
    """
    if _api_backend_active(printer_name or ""):
        model = _model_for_exe(_exe_for_model(_preferred_model_for_printer(printer_name or "")) or "") or "pro"
        if magnification and not size:
            logger.warning("직접 호출 경로는 상대 배율(-R)을 아직 지원하지 않습니다 — 절대 크기로 넘겨야 합니다.")
        rc, lines = _make_arxp_isolated(
            image_path, arx4_path, model,
            position or config.POSITION, size or "", option_overrides or {},
        )
        for line in lines:
            logger.info("%s", line)
        if rc is None:
            return -1401
        if rc != 0:
            desc = RETURN_CODES.get(rc, f"알 수 없는 에러 ({rc})")
            logger.error("가먼트 API 직접 호출 실패 (rc=%s): %s", rc, desc)
        return rc

    args = [
        "print",
        "-X", xml_path,
        "-I", image_path,
        "-A", arx4_path,
        "-L", position or config.POSITION,
    ]
    if size:
        args += ["-S", size]
    if magnification:
        args += ["-R", magnification]
    if white is not None:
        args += ["-W", str(white)]
    return _run_with_probe(args, printer_name=printer_name)


def send_to_printer(arx4_path: str, printer_name: str = None) -> int:
    """인쇄 데이터 → 프린터 전송."""
    target = printer_name or config.PRINTER_NAME
    if _api_backend_active(target or ""):
        model = _model_for_exe(_exe_for_model(_preferred_model_for_printer(target or "")) or "") or "pro"
        rc, lines = garment_api.send(arx4_path, target, model=model)
        for line in lines:
            logger.info("%s", line)
        if rc is None:
            return -1801
        if rc != 0:
            logger.error("가먼트 API 전송 실패 (rc=%s)", rc)
        return rc
    args = ["send", "-A", arx4_path, "-P", target]
    # -D(인쇄 후 자동 작업 삭제)는 GTXpro CMD 전용 옵션이다. GTX-4 CMD send 에
    # 넘기면 -3301(option cannot be used with send)로 실패하므로 pro 에서만 부여한다.
    # 값은 config.GARMENT_AUTO_DELETE 로 조절(기본 0=삭제 안 함, 장비 수신 이력 보존).
    if preferred_data_extension(target) == ".arxp":
        args += ["-D", "1" if config.GARMENT_AUTO_DELETE else "0"]
        logger.info(
            "  작업 삭제(GTXpro -D): %s",
            "삭제(-D 1)" if config.GARMENT_AUTO_DELETE else "보존(-D 0)",
        )
    else:
        # GTX-4(422/legacy)는 CLI에 -D/작업삭제 제어가 없다(가이드 §3-2/§3-4).
        # 수신 이력 보존 여부는 장비 패널 'Auto Job Delete' 설정이 전적으로 결정한다.
        logger.info(
            "  작업 삭제(GTX-4/422): CLI 미지원 — 장비 'Auto Job Delete' 패널 설정을 따름"
        )
    return _run(args, printer_name=target)


def extract_data(arx4_path: str, xml_path: str = None,
                 image_path: str = None, size: str = None,
                 printer_name: str = None) -> int:
    """ARX4 → XML/이미지 추출."""
    args = ["extract", "-A", arx4_path]
    if xml_path:
        args += ["-X", xml_path]
    if image_path:
        args += ["-I", image_path]
    if size:
        args += ["-S", size]
    return _run(args, printer_name=printer_name)


def get_status(printer_name: str = None, status_csv: str = None,
               option_csv: str = None, maint_csv: str = None) -> int:
    """프린터 상태 CSV 출력 (LAN 전용)."""
    args = ["status", "-P", printer_name or config.PRINTER_NAME]
    if status_csv:
        args += ["-S", status_csv]
    if option_csv:
        args += ["-O", option_csv]
    if maint_csv:
        args += ["-M", maint_csv]
    return _run(args)


# Printer Status 비트 (가이드 §3-5-2, legacy/pro 공통)
_PS_INITIALIZING = 0x01
_PS_STANDBY = 0x02
_PS_READY = 0x04
_PS_PRINTING = 0x08
_PS_MENU_ACTIVE = 0x10
_PS_ERROR_STOP = 0x20

# 에러코드 행 — 심각(error) vs 경고(warning) 구분. (가이드 샘플 오타 "Usal Error" 병행 매칭)
_FATAL_KEYS = ("Fatal Error", "Fatal Error2", "Usual Error", "Usal Error")
_WARN_KEYS = ("Wait OK", "Wait OK2", "Warning")


def read_printer_status(printer_name: str = None) -> dict | None:
    """프린터 status CSV 를 조회·파싱해 상태 dict 반환. 실패 시 None.

    status 명령은 LAN 연결 프린터 전용이므로, USB 연결/미연결/조회 실패 시
    None 을 돌려준다(= 오프라인). GTXpro 는 Current File/Current JobID 까지
    제공하나 legacy(GTX-4) 는 Printer Status 비트 + 에러코드만 제공한다.
    """
    target = printer_name or config.PRINTER_NAME
    if not target:
        return None
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="gtx_status_")
    os.close(fd)
    try:
        rc = get_status(target, status_csv=path)
        if rc != 0 or not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8-sig", errors="ignore", newline="") as f:
            rows = list(csv.reader(f))
    except Exception:
        logger.debug("status CSV 조회/파싱 실패", exc_info=True)
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    return _parse_status_rows(rows)


def _parse_status_rows(rows: list) -> dict | None:
    """status CSV 행들을 상태 dict 로 변환. Printer Status 가 없으면 None."""
    fields: dict[str, list[str]] = {}
    for row in rows:
        if not row:
            continue
        key = (row[0] or "").strip()
        if key:
            fields[key] = [c.strip() for c in row[1:]]

    raw = (fields.get("Printer Status") or [""])[0]
    if raw == "":
        return None
    try:
        value = int(raw, 16)
    except ValueError:
        return None

    errors = [
        f"{k}: {', '.join(c for c in fields[k] if c not in ('', '0'))}"
        for k in _FATAL_KEYS
        if k in fields and any(c not in ("", "0") for c in fields[k])
    ]
    warnings = [
        f"{k}: {', '.join(c for c in fields[k] if c not in ('', '0'))}"
        for k in _WARN_KEYS
        if k in fields and any(c not in ("", "0") for c in fields[k])
    ]

    error_stop = bool(value & _PS_ERROR_STOP)
    printing = bool(value & _PS_PRINTING)
    ready = bool(value & _PS_READY)
    standby = bool(value & _PS_STANDBY)
    initializing = bool(value & _PS_INITIALIZING)
    menu_active = bool(value & _PS_MENU_ACTIVE)
    has_error = error_stop or bool(errors)

    if has_error:
        state = "error"
    elif printing:
        state = "printing"
    elif initializing:
        state = "init"
    elif ready:
        state = "ready"
    elif standby:
        state = "standby"
    elif menu_active:
        state = "menu"
    else:
        state = "unknown"

    def _first(key):
        v = fields.get(key) or [""]
        return v[0] or None

    return {
        "raw": raw,
        "value": value,
        "printing": printing,
        "ready": ready,
        "standby": standby,
        "initializing": initializing,
        "menu_active": menu_active,
        "error_stop": error_stop,
        "error": has_error,
        "warning": bool(warnings),
        "state": state,
        "errors": errors,
        "warnings": warnings,
        "current_file": _first("Current File"),
        "current_jobid": _first("Current JobID"),
    }


def circulation(printer_name: str = None) -> int:
    """화이트 잉크 순환 (LAN 전용)."""
    return _run(["Circulation", "-P", printer_name or config.PRINTER_NAME])


def auto_cleaning(printer_name: str = None) -> int:
    """자동 클리닝 (LAN 전용)."""
    return _run(["AutoCleaning", "-P", printer_name or config.PRINTER_NAME])


def print_disable(printer_name: str = None) -> int:
    """인쇄 버튼 비활성화 (LAN 전용)."""
    return _run(["PrintDisable", "-P", printer_name or config.PRINTER_NAME])


def print_enable(printer_name: str = None) -> int:
    """인쇄 버튼 활성화 (LAN 전용)."""
    return _run(["PrintEnable", "-P", printer_name or config.PRINTER_NAME])


def menu_lock(printer_name: str = None) -> int:
    """메뉴 잠금 (LAN 전용)."""
    return _run(["MenuLock", "-P", printer_name or config.PRINTER_NAME])


def menu_unlock(printer_name: str = None) -> int:
    """메뉴 해제 (LAN 전용)."""
    return _run(["MenuUnlock", "-P", printer_name or config.PRINTER_NAME])


def get_log(printer_name: str = None, log_path: str = "") -> int:
    """프린터 로그 다운로드 (LAN 전용)."""
    return _run([
        "getlog",
        "-P", printer_name or config.PRINTER_NAME,
        "-L", log_path,
    ])


def pick_log(log_path: str, print_csv: str = None,
             oper_csv: str = None, maint_csv: str = None,
             start: str = None, end: str = None) -> int:
    """로그에서 이력 CSV 추출."""
    args = ["picklog", "-L", log_path]
    if print_csv:
        args += ["-P", print_csv]
    if oper_csv:
        args += ["-O", oper_csv]
    if maint_csv:
        args += ["-M", maint_csv]
    if start:
        args += ["-S", start]
    if end:
        args += ["-E", end]
    return _run(args)
