"""GTX4CMD.exe CLI 래퍼 - subprocess로 호출, 리턴 코드 해석."""

import logging
import subprocess

import config

logger = logging.getLogger(__name__)

RETURN_CODES = {
    0: "성공",
    -1001: "드라이버 파일 없음",
    -1403: "프린터를 찾을 수 없거나 드라이버 사용 불가",
    -2001: "PNG 파일이 아니거나 로드 불가",
    -2401: "프린터 미발견 또는 LAN 미연결",
    -2701: "프린터 연결 실패",
    -3102: "XML 파일 없음",
    -3103: "이미지 파일 없음",
    -3104: "-P와 -A 동시 지정 불가",
}


def _run(args: list) -> int:
    """GTX4CMD.exe 실행, 리턴 코드 반환."""
    exe = config.GTX4CMD_EXE
    if not exe:
        raise FileNotFoundError(
            "GTX4CMD.exe 경로가 설정되지 않았습니다. "
            "config.ini [gtx4cmd] exe_path를 확인하세요."
        )
    cmd = [exe] + args
    logger.debug("실행: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    rc = result.returncode
    if rc != 0:
        desc = RETURN_CODES.get(rc, f"알 수 없는 에러 ({rc})")
        logger.error("GTX4CMD 에러: %s", desc)
    return rc


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
