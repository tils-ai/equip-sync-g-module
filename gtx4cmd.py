"""GTX4CMD.exe CLI 래퍼 - subprocess로 호출, 리턴 코드 해석."""

import logging
import os
import subprocess

import config

logger = logging.getLogger(__name__)

RETURN_CODES = {
    0: "성공",
    -1001: "드라이버 파일 없음 — Brother GTX-4 프린터 드라이버 설치 확인",
    -1401: "드라이버 파일 없음 — Brother GTX-4 프린터 드라이버/GTX4Api.dll 위치 확인",
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

# 파일/DLL 누락 계열 — 발생 시 관련 폴더 listing 을 진단 로그로 남긴다.
_FILE_MISSING_CODES = {-1001, -1401, -2001, -3102, -3103}


def _log_dir_listing(label: str, dir_path: str) -> None:
    """진단용: 디렉토리 항목을 ERROR 레벨로 출력. 경로 누락/조회 실패도 명시."""
    if not dir_path:
        logger.error("  %s: (경로 없음)", label)
        return
    if not os.path.isdir(dir_path):
        logger.error("  %s: %s — 폴더가 존재하지 않음", label, dir_path)
        return
    try:
        entries = sorted(os.listdir(dir_path))
    except OSError as e:
        logger.error("  %s: %s — 목록 조회 실패: %s", label, dir_path, e)
        return
    logger.error("  %s: %s (항목 %d개)", label, dir_path, len(entries))
    for name in entries:
        full = os.path.join(dir_path, name)
        if os.path.isdir(full):
            logger.error("    [D] %s", name)
        else:
            try:
                size = os.path.getsize(full)
                logger.error("    [F] %s (%d bytes)", name, size)
            except OSError:
                logger.error("    [F] %s (크기 조회 실패)", name)


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


def _run(args: list) -> int:
    """GTX4CMD.exe 실행, 리턴 코드 반환."""
    exe = config.GTX4CMD_EXE
    if not exe:
        raise FileNotFoundError(
            "GTX4CMD.exe 경로가 설정되지 않았습니다. "
            "config.ini [gtx4cmd] exe_path를 확인하세요."
        )
    cmd = [exe] + args
    # GTX4CMD.exe 와 동봉 DLL/드라이버 자료가 같은 폴더에 있어야 정상 동작.
    # cwd 를 exe 폴더로 강제해 Graphiclabs 와 동일한 실행 컨텍스트 보장.
    cwd = os.path.dirname(exe) or None
    logger.debug("실행 (cwd=%s): %s", cwd, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, timeout=120, cwd=cwd)
    rc = _normalize_returncode(result.returncode)
    if rc != 0:
        desc = RETURN_CODES.get(rc, f"알 수 없는 에러 ({rc})")
        logger.error("GTX4CMD 에러 (rc=%d): %s", rc, desc)
        stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        if stdout:
            logger.error("GTX4CMD stdout: %s", stdout)
        if stderr:
            logger.error("GTX4CMD stderr: %s", stderr)
        if rc in _FILE_MISSING_CODES:
            _log_diagnostics(exe, cwd, args, rc)
    return rc


def _log_diagnostics(exe: str, cwd: str | None, args: list, rc: int) -> None:
    """파일/DLL 누락 에러(-1001/-1401/-2001/-3102/-3103) 발생 시 경로·폴더 내용을 덤프."""
    logger.error("진단 정보 (rc=%d):", rc)
    logger.error("  GTX4CMD.exe 경로: %s (존재=%s)", exe, os.path.isfile(exe))
    logger.error("  실행 cwd: %s", cwd or "(미지정)")
    logger.error("  전달 args: %s", " ".join(args))

    # 드라이버/DLL 누락 계열 — exe 와 같은 폴더에 GTX4Api.dll 등 동봉 자료가 있어야 함.
    if rc in (-1001, -1401):
        _log_dir_listing("GTX4CMD.exe 폴더", cwd or os.path.dirname(exe))

    # 입력 파일 누락 계열 — 해당 파일의 상위 폴더 내용을 보여줌.
    if rc == -2001:  # PNG 로드 불가
        img = _extract_arg_path(args, "-I")
        if img:
            logger.error("  이미지 경로: %s (존재=%s)", img, os.path.isfile(img))
            _log_dir_listing("이미지 폴더", os.path.dirname(img))
    if rc == -3102:  # XML 파일 없음
        xml = _extract_arg_path(args, "-X")
        if xml:
            logger.error("  XML 경로: %s (존재=%s)", xml, os.path.isfile(xml))
            _log_dir_listing("XML 폴더", os.path.dirname(xml))
    if rc == -3103:  # 이미지 파일 없음
        img = _extract_arg_path(args, "-I")
        if img:
            logger.error("  이미지 경로: %s (존재=%s)", img, os.path.isfile(img))
            _log_dir_listing("이미지 폴더", os.path.dirname(img))


def create_arx4(xml_path: str, image_path: str, arx4_path: str,
                position: str = None, size: str = None,
                magnification: str = None, white: int = None) -> int:
    """PNG + XML → ARX4 생성."""
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
    return _run(args)


def send_to_printer(arx4_path: str, printer_name: str = None) -> int:
    """ARX4 → 프린터 전송."""
    return _run([
        "send",
        "-A", arx4_path,
        "-P", printer_name or config.PRINTER_NAME,
    ])


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
