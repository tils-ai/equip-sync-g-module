import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

import win32print
import win32ui
from PIL import Image, ImageWin

import config

logger = logging.getLogger(__name__)

# 갓 만들어진 PDF 를 다른 프로세스가 곧바로 열지 못하는 경우가 있다(백신 실시간 검사 등).
# 잠깐 뒤에는 읽히는 일이 잦아 짧게 되풀이한다.
_CONVERT_RETRIES = 10
_CONVERT_RETRY_DELAY = 0.2

_poppler_logged = False


def list_printers() -> list[str]:
    """Windows에 설치된 프린터 이름 목록을 반환한다.

    Windows 외 환경(개발/DRYRUN)에서는 빈 리스트를 반환한다.
    """
    if sys.platform != "win32":
        return []
    try:
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        return [p[2] for p in printers]
    except Exception:
        logger.exception("프린터 목록 조회 실패")
        return []


def _ensure_printer_installed(printer_name: str) -> None:
    """설치된 프린터 목록에 printer_name 이 있는지 검증.

    Windows 외 환경에서는 list_printers 가 빈 리스트라 검증을 스킵한다 (개발용).
    """
    if not printer_name:
        raise RuntimeError("프린터 이름이 비어 있습니다.")
    installed = list_printers()
    if not installed:
        return
    if printer_name not in installed:
        raise RuntimeError(
            f"설정된 프린터를 찾을 수 없습니다: '{printer_name}'. "
            f"설치된 프린터 목록: {installed}"
        )


def _ansi_codepage() -> str:
    """시스템 ANSI 코드페이지. poppler 같은 비유니코드 exe 가 인자를 해석하는 기준이다."""
    try:
        import ctypes

        return str(ctypes.windll.kernel32.GetACP())
    except Exception:
        return "조회 실패"


def _poppler_exe(name: str) -> str:
    """poppler 실행파일 경로. POPPLER_PATH 가 없으면 이름만 넘겨 PATH 에 맡긴다."""
    exe = f"{name}.exe" if sys.platform == "win32" else name
    poppler = getattr(config, "POPPLER_PATH", None)
    return os.path.join(poppler, exe) if poppler else exe


def _run_poppler(args: list[str], timeout: int = 15) -> tuple[int | None, str, str]:
    """poppler 보조 실행 → (종료코드, stdout, stderr). 실행 자체가 실패하면 종료코드 None.

    `stdin=DEVNULL` 은 의도적이다 — `--windowed` 로 빌드한 EXE 는 표준입력 핸들이 없어,
    그대로 물려주면 자식 프로세스가 곧바로 죽는 경우가 있다.
    """
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (
            proc.returncode,
            proc.stdout.decode("utf-8", "ignore"),
            proc.stderr.decode("utf-8", "ignore"),
        )
    except Exception as e:
        return None, "", f"{type(e).__name__}: {e}"


def log_poppler_once() -> None:
    """poppler 위치·버전을 최초 1회 로그에 남긴다.

    작업지시서 출력은 poppler 에 의존하는데 지금까지 로그에 아무 흔적도 없어,
    설정이 먹었는지조차 현장에 물어봐야 했다.
    """
    global _poppler_logged
    if _poppler_logged:
        return
    _poppler_logged = True

    path = getattr(config, "POPPLER_PATH", None)
    source = getattr(config, "POPPLER_SOURCE", "") or "미상"
    exe = _poppler_exe("pdfinfo")
    logger.info("poppler 경로: %s (출처=%s)", path or "(미지정 — 시스템 PATH)", source)
    logger.info("poppler pdfinfo: %s (존재=%s)", exe, os.path.isfile(exe) if path else "PATH 탐색")

    code, out, err = _run_poppler([exe, "-v"])
    version = (out or err).strip().splitlines()
    if code == 0 and version:
        logger.info("poppler 버전: %s", version[0])
    else:
        logger.error(
            "poppler 실행 확인 실패 — 종료코드=%s stdout=%s stderr=%s. "
            "작업지시서 출력이 되지 않을 수 있습니다.",
            code, (out.strip() or "(비어 있음)"), (err.strip() or "(비어 있음)"),
        )


def _ascii_safe_pdf(pdf_path: str) -> tuple[str, bool]:
    """poppler 에 넘길 ASCII 전용 사본을 만든다 → (쓸 경로, 임시본 여부).

    poppler 는 Windows 에서 유니코드 경로에 약하다. 같은 실행파일이 `-v` 는 멀쩡히
    답하면서 한글이 든 경로를 인자로 주면 종료코드 0 에 출력 0 으로 끝나는 것을
    현장에서 확인했다(2026-09-17 영등포점). 지시서 파일명에는 `_지시서.pdf` 가
    늘 들어가므로 변환 직전에 ASCII 경로로 복사해 그 사본을 넘긴다.

    만들지 못하면 원본 경로를 그대로 돌려준다 — 지금보다 나빠지지 않는다.
    """
    if pdf_path.isascii():
        return pdf_path, False
    try:
        tmp_dir = tempfile.gettempdir()
        if not tmp_dir.isascii():
            logger.warning("임시 폴더 경로에도 비ASCII 문자가 있어 원본 경로를 그대로 쓴다: %s", tmp_dir)
            return pdf_path, False
        fd, tmp_path = tempfile.mkstemp(prefix="eqg-wo-", suffix=".pdf", dir=tmp_dir)
        os.close(fd)
        shutil.copyfile(pdf_path, tmp_path)
        logger.info("작업지시서 PDF 를 ASCII 경로로 복사해 변환한다: %s", tmp_path)
        return tmp_path, True
    except Exception:
        logger.exception("ASCII 사본 생성 실패 — 원본 경로로 진행한다")
        return pdf_path, False


def _log_pdf_diagnostics(pdf_path: str) -> None:
    """변환이 끝내 실패했을 때 원인을 좁힐 정보를 남긴다.

    pdf2image 는 poppler 의 stderr 를 예외 메시지에 붙이지만 그 출력이 비어 있으면
    단서가 하나도 남지 않는다. 그래서 같은 pdfinfo 를 직접 한 번 더 돌려
    종료코드·표준출력·표준오류와 파일 상태를 함께 적는다.
    """
    try:
        exists = os.path.exists(pdf_path)
        size = os.path.getsize(pdf_path) if exists else -1
        readable = os.access(pdf_path, os.R_OK) if exists else False
        logger.error(
            "  진단 — 파일 존재=%s 크기=%s bytes 읽기가능=%s 경로=%s",
            exists, size, readable, pdf_path,
        )
        logger.error(
            "  진단 — 경로 ASCII=%s / 시스템 ANSI 코드페이지=%s",
            pdf_path.isascii(), _ansi_codepage(),
        )
        code, out, err = _run_poppler([_poppler_exe("pdfinfo"), pdf_path])
        logger.error("  진단 — pdfinfo 종료코드=%s", code)
        logger.error("  진단 — pdfinfo stdout: %s", out.strip() or "(비어 있음)")
        logger.error("  진단 — pdfinfo stderr: %s", err.strip() or "(비어 있음)")
        if code == 0 and "Pages:" in out:
            logger.error(
                "  진단 — 직접 호출은 성공했다. pdf2image 경유만 실패하므로 "
                "호출 방식(표준입력 핸들 등) 차이를 의심한다."
            )
    except Exception:
        logger.exception("  진단 수집 실패")


def print_pdf_general(pdf_path: str, printer_name: str, dpi: int = 200) -> None:
    """PDF 파일을 일반 Windows 프린터로 출력 (작업지시서용).

    pdf2image로 페이지별 PIL Image로 변환 후 print_image() 재사용.
    가먼트 프린터가 아닌 일반 A4 레이저/잉크젯에 보낸다.
    """
    if not printer_name:
        raise RuntimeError("작업지시서 프린터명이 설정되지 않았습니다.")
    _ensure_printer_installed(printer_name)
    from pdf2image import convert_from_path

    log_poppler_once()

    poppler = getattr(config, "POPPLER_PATH", None)
    source_pdf, is_temp = _ascii_safe_pdf(pdf_path)
    images = None
    last_error: Exception | None = None
    try:
        for attempt in range(1, _CONVERT_RETRIES + 1):
            try:
                images = convert_from_path(
                    source_pdf, dpi=dpi, poppler_path=poppler, use_pdftocairo=True
                )
                if attempt > 1:
                    logger.info("작업지시서 PDF 변환 성공 (%d회차)", attempt)
                break
            except Exception as e:
                last_error = e
                if attempt < _CONVERT_RETRIES:
                    logger.warning(
                        "작업지시서 PDF 변환 실패 (%d/%d) — %.1f초 뒤 재시도: %s",
                        attempt, _CONVERT_RETRIES, _CONVERT_RETRY_DELAY, e,
                    )
                    time.sleep(_CONVERT_RETRY_DELAY)

        if images is None:
            logger.error(
                "작업지시서 PDF 변환이 %d회 모두 실패했습니다: %s%s",
                _CONVERT_RETRIES,
                source_pdf,
                f" (원본: {pdf_path})" if is_temp else "",
            )
            _log_pdf_diagnostics(source_pdf)
            raise last_error
    finally:
        # 변환된 이미지는 메모리에 올라오므로 사본은 여기서 지워도 된다
        if is_temp:
            try:
                os.remove(source_pdf)
            except OSError:
                pass

    if not images:
        raise RuntimeError(f"PDF에 페이지가 없습니다: {pdf_path}")
    for i, img in enumerate(images, 1):
        logger.info("작업지시서 페이지 %d/%d 출력 중 (%s)...", i, len(images), printer_name)
        print_image(img, printer_name)


def print_image(image: Image.Image, printer_name: str = None):
    """PIL 이미지를 Windows 프린터로 직접 출력한다."""
    printer_name = printer_name or config.PRINTER_NAME
    _ensure_printer_installed(printer_name)

    hdc = win32ui.CreateDC()
    try:
        hdc.CreatePrinterDC(printer_name)
    except Exception as e:
        installed = list_printers()
        raise RuntimeError(
            f"프린터를 열 수 없습니다: '{printer_name}'. "
            f"Windows 에서 이 이름의 프린터를 찾지 못했거나 오프라인 상태입니다. "
            f"설치된 프린터: {installed} (원인: {e})"
        ) from e

    try:
        pw = hdc.GetDeviceCaps(110)   # PHYSICALWIDTH
        ph = hdc.GetDeviceCaps(111)   # PHYSICALHEIGHT

        # 프린터 너비에 맞춰 비율 유지 스케일링
        ratio = pw / image.width
        new_w = pw
        new_h = int(image.height * ratio)
        if new_h > ph:
            ratio = ph / image.height
            new_w = int(image.width * ratio)
            new_h = ph

        hdc.StartDoc("GTX4 Print")
        hdc.StartPage()
        dib = ImageWin.Dib(image)
        dib.draw(hdc.GetHandleOutput(), (0, 0, new_w, new_h))
        hdc.EndPage()
        hdc.EndDoc()
        logger.info("출력 완료: %dx%d → %dx%d", image.width, image.height, new_w, new_h)
    finally:
        hdc.DeleteDC()
