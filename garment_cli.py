"""가먼트 CLI 래퍼 - subprocess로 호출, 리턴 코드 해석.

legacy/pro 두 계열의 가먼트 CLI 를 auto-probe 로 선택한다(실제 벤더 도구는 빌드 시 중립명으로 복원됨).
"""

import datetime
import logging
import os
import subprocess

import config

logger = logging.getLogger(__name__)

RETURN_CODES = {
    0: "성공",
    -1001: "드라이버 파일 없음 — 가먼트 프린터 드라이버 설치 확인",
    -1401: "드라이버 파일 없음 — 가먼트 프린터 드라이버/API 라이브러리 위치 확인",
    -1402: "메모리 할당 실패",
    -1403: "프린터를 찾을 수 없거나 드라이버 사용 불가",
    -2001: "PNG 파일이 아니거나 로드 불가",
    -2401: "프린터 미발견 또는 LAN 미연결",
    -2701: "프린터 연결 실패",
    -3102: "XML 파일 없음",
    -3103: "이미지 파일 없음",
    -3104: "-P와 -A 동시 지정 불가",
    -3108: "-S 와 -R 동시 지정 불가 또는 둘 다 미지정",
}

# 파일/DLL 누락·드라이버 로드 실패 계열 — 발생 시 별도 진단 .txt 파일을 생성한다.
_FILE_MISSING_CODES = {-1001, -1401, -1403, -2001, -3102, -3103}

# 드라이버/장비 매칭 실패 계열 — "이 CLI 가 이 장비에 안 맞음" 신호.
# 이 코드일 때만 다른 계열(legacy ↔ pro)의 가먼트 CLI 로 fallback 한다.
# (-2001/-3102/-3103 같은 입력 오류는 다른 CLI 로도 동일 실패하므로 제외)
_DRIVER_MISMATCH_CODES = {-1001, -1401, -1403, -1701}

# auto-probe 로 확정된 가먼트 CLI exe 경로 (프로세스 메모리 캐시).
_active_exe: str | None = None


def _model_for_exe(exe: str) -> str:
    base = os.path.basename(exe or "").lower()
    if "pro" in base:
        return "pro"
    if "legacy" in base:
        return "legacy"
    return ""


def _exe_for_model(model: str) -> str:
    return {"legacy": config.LEGACY_CLI_EXE, "pro": config.PRO_CLI_EXE}.get(model, "")


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


def _candidate_exes() -> list:
    """probe 후보 — 캐시된 CLI 우선, 그다음 legacy/pro 계열 중 실제 존재하는 것 (중복 제거)."""
    out = []
    for exe in (_load_active_exe(), config.LEGACY_CLI_EXE, config.PRO_CLI_EXE):
        if exe and os.path.isfile(exe) and exe not in out:
            out.append(exe)
    return out


def describe_cli_selection() -> str:
    """Return the GTX CLI mode currently selected for logging."""
    active = _load_active_exe()
    candidates = _candidate_exes()
    active_label = _model_for_exe(active) if active else "auto"
    candidate_labels = [
        f"{_model_for_exe(exe) or 'unknown'}:{os.path.basename(exe)}"
        for exe in candidates
    ]
    return (
        f"garment_mode={config.GARMENT_MODE}, "
        f"gtx_cli={active_label}, "
        f"candidates={', '.join(candidate_labels) or '(none)'}"
    )


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


def _run(args: list, exe: str = None, printer_name: str = None) -> int:
    """가먼트 CLI 실행, 리턴 코드 반환.

    exe 미지정 시 auto-probe 로 확정된 CLI → legacy 계열 순으로 사용한다.
    (send/status/제어 등은 exe 를 넘기지 않으므로 자동으로 확정 CLI 를 재사용)
    """
    if exe is None:
        exe = _load_active_exe() or config.LEGACY_CLI_EXE
    if not exe:
        raise FileNotFoundError(
            "가먼트 CLI 경로가 설정되지 않았습니다. "
            "config.ini [garment_cli] cli_legacy_path / cli_pro_path 또는 .source 폴더를 확인하세요."
        )
    cmd = [exe] + args
    # CLI exe 와 동봉 DLL/드라이버 자료가 같은 폴더에 있어야 정상 동작.
    # cwd 를 exe 폴더로 강제해 Graphiclabs 와 동일한 실행 컨텍스트 보장.
    cwd = os.path.dirname(exe) or None
    logger.debug("실행 (cwd=%s): %s", cwd, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, timeout=120, cwd=cwd)
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
        if rc in _FILE_MISSING_CODES:
            try:
                report_path = _write_diagnostic_report(
                    exe, cwd, args, rc, result.stdout, result.stderr,
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
    """PE 헤더 IMAGE_FILE_MACHINE → 아키텍처 문자열."""
    if not os.path.isfile(path):
        return "(파일 없음)"
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                return "PE 아님 (MZ 시그니처 없음)"
            f.seek(0x3C)
            pe_offset = int.from_bytes(f.read(4), "little")
            f.seek(pe_offset)
            if f.read(4) != b"PE\x00\x00":
                return "PE 시그니처 없음"
            machine = int.from_bytes(f.read(2), "little")
    except OSError as e:
        return f"확인 실패: {e}"
    return {
        0x014C: "x86 (32-bit)",
        0x8664: "x64 (64-bit)",
        0xAA64: "ARM64",
    }.get(machine, f"알 수 없음 (machine=0x{machine:04X})")


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
    L.append(f"  GTX mode     : {describe_cli_selection()}")
    L.append(f"  Printer info : {printer_driver_summary(target_printer)}")

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
        "if ($d) { ($d | Select-Object Name,Manufacturer,InfPath | "
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

    print(-A) 는 실제 장비로 전송하지 않으므로 둘 다 시도해도 부작용이 없다.
    여기서 확정된 CLI 를 send/status/제어가 재사용한다(잘못된 CLI 의 중복 전송 방지).
    """
    candidates = _candidate_exes()
    if not candidates:
        return _run(args, printer_name=printer_name)  # 설정 없음 → 기존 경로(FileNotFoundError) 위임
    last_rc = None
    for exe in candidates:
        rc = _run(args, exe=exe, printer_name=printer_name)
        if rc == 0:
            if exe != _active_exe:
                _save_active_exe(exe)
                logger.info("가먼트 CLI 확정: %s", os.path.basename(exe))
            return 0
        if rc not in _DRIVER_MISMATCH_CODES:
            return rc  # 입력 오류 등 — fallback 무의미
        last_rc = rc
    logger.error("모든 가먼트 CLI 매칭 실패 (마지막 rc=%s)", last_rc)
    _clear_active_exe()
    return last_rc if last_rc is not None else -1401


def create_arx4(xml_path: str, image_path: str, arx4_path: str,
                position: str = None, size: str = None,
                magnification: str = None, white: int = None,
                printer_name: str = None) -> int:
    """PNG + XML → ARX4 생성. (가먼트 CLI auto-probe 진입점)"""
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
    """ARX4 → 프린터 전송."""
    return _run([
        "send",
        "-A", arx4_path,
        "-P", printer_name or config.PRINTER_NAME,
    ], printer_name=printer_name or config.PRINTER_NAME)


def extract_data(arx4_path: str, xml_path: str = None,
                 image_path: str = None, size: str = None) -> int:
    """ARX4 → XML/이미지 추출."""
    args = ["extract", "-A", arx4_path]
    if xml_path:
        args += ["-X", xml_path]
    if image_path:
        args += ["-I", image_path]
    if size:
        args += ["-S", size]
    return _run(args)


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
