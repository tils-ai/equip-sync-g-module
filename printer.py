import glob
import logging
import os
import re
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


def _page_no(path: str) -> int:
    """pdftocairo 가 붙인 꼬리 번호. page-2 가 page-10 뒤로 가지 않게 숫자로 정렬한다."""
    m = re.search(r"-(\d+)\.png$", path)
    return int(m.group(1)) if m else 0


def _render_with_pdftocairo(pdf_path: str, dpi: int) -> list[Image.Image]:
    """pdftocairo 로 PDF 를 PNG 파일로 직접 뽑아 PIL 이미지로 읽는다.

    `pdf2image.convert_from_path` 는 페이지 수를 알아내려고 **pdfinfo 의 stdout 을
    파싱**하는데, 영등포점에서 그 호출이 종료코드 0 에 출력 0 으로 끝나 변환이
    시작도 못 했다(2026-09-17). 같은 실행파일을 cmd 에서 부르면 멀쩡해 원인을
    못 좁혔다.

    pdftocairo 는 결과를 **파일로** 쓰므로 그 구간을 지나가지 않는다.
    페이지 수도 생성된 파일 개수로 알 수 있어 따로 물어볼 필요가 없다.
    """
    out_dir = tempfile.mkdtemp(prefix="eqg-wo-")
    try:
        prefix = os.path.join(out_dir, "page")
        code, out, err = _run_poppler(
            [_poppler_exe("pdftocairo"), "-png", "-r", str(dpi), pdf_path, prefix],
            timeout=120,
        )
        files = sorted(glob.glob(prefix + "-*.png"), key=_page_no)
        if not files:
            raise RuntimeError(
                f"pdftocairo 가 이미지를 만들지 못했습니다 "
                f"(종료코드={code}, stdout={out.strip() or '없음'}, stderr={err.strip() or '없음'})"
            )
        images = []
        for f in files:
            with Image.open(f) as im:
                images.append(im.copy())
        return images
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


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

    # 1차 — pdftocairo 직접. pdfinfo 의 stdout 을 읽지 않아 그 구간을 지나가지 않는다.
    try:
        images = _render_with_pdftocairo(pdf_path, dpi)
        logger.info("작업지시서 렌더: pdftocairo 직접 (%d쪽)", len(images))
        for i, img in enumerate(images, 1):
            logger.info("작업지시서 페이지 %d/%d 출력 중 (%s)...", i, len(images), printer_name)
            print_image(img, printer_name, fit_printable=True)
        return
    except Exception as e:
        logger.warning("pdftocairo 직접 렌더 실패 — pdf2image 로 폴백: %s", e)

    # 2차 — 기존 경로. 여기서도 실패하면 진단을 남긴다.
    images = None
    last_error: Exception | None = None
    for attempt in range(1, _CONVERT_RETRIES + 1):
        try:
            images = convert_from_path(
                pdf_path, dpi=dpi, poppler_path=poppler, use_pdftocairo=True
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
        logger.error("작업지시서 PDF 변환이 %d회 모두 실패했습니다: %s", _CONVERT_RETRIES, pdf_path)
        _log_pdf_diagnostics(pdf_path)
        raise last_error

    if not images:
        raise RuntimeError(f"PDF에 페이지가 없습니다: {pdf_path}")
    for i, img in enumerate(images, 1):
        logger.info("작업지시서 페이지 %d/%d 출력 중 (%s)...", i, len(images), printer_name)
        print_image(img, printer_name, fit_printable=True)


def print_image(image: Image.Image, printer_name: str = None, fit_printable: bool = False):
    """PIL 이미지를 Windows 프린터로 직접 출력한다.

    `fit_printable=True` 는 **인쇄 가능 영역**(HORZRES/VERTRES)에 맞춰 그리고 가운데 정렬한다.
    작업지시서(A4 일반 프린터)가 이쪽이다. 용지 전체 크기로 그리면 프린터가 인쇄할 수 없는
    여백만큼 밀려 위아래가 잘린다 — 여백이 큰 기종일수록 심하다.

    기본값(False)은 용지 전체 크기(PHYSICALWIDTH/HEIGHT) 기준에 좌상단 고정으로,
    가먼트 direct 출력이 쓰던 **기존 동작 그대로**다. 의류 위 디자인 위치가 달라지면
    안 되므로 건드리지 않는다.
    """
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
        if fit_printable:
            area_w = hdc.GetDeviceCaps(8)     # HORZRES  — 인쇄 가능 폭
            area_h = hdc.GetDeviceCaps(10)    # VERTRES  — 인쇄 가능 높이
        else:
            area_w = hdc.GetDeviceCaps(110)   # PHYSICALWIDTH  — 용지 전체
            area_h = hdc.GetDeviceCaps(111)   # PHYSICALHEIGHT

        # 폭에 맞춘 뒤 높이가 넘치면 높이 기준으로 다시 맞춘다 (비율 유지)
        ratio = area_w / image.width
        new_w = area_w
        new_h = int(image.height * ratio)
        if new_h > area_h:
            ratio = area_h / image.height
            new_w = int(image.width * ratio)
            new_h = area_h

        # 가운데 정렬은 인쇄 가능 영역 기준일 때만. 기존 경로는 좌상단 고정을 유지한다.
        off_x = (area_w - new_w) // 2 if fit_printable else 0
        off_y = (area_h - new_h) // 2 if fit_printable else 0

        hdc.StartDoc("GTX4 Print")
        hdc.StartPage()
        dib = ImageWin.Dib(image)
        dib.draw(hdc.GetHandleOutput(), (off_x, off_y, off_x + new_w, off_y + new_h))
        hdc.EndPage()
        hdc.EndDoc()
        logger.info(
            "출력 완료: %dx%d → %dx%d @(%d,%d) [%s 영역 %dx%d]",
            image.width, image.height, new_w, new_h, off_x, off_y,
            "인쇄가능" if fit_printable else "용지전체", area_w, area_h,
        )
    finally:
        hdc.DeleteDC()
