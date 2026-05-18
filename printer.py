import logging
import sys

import win32print
import win32ui
from PIL import Image, ImageWin

import config

logger = logging.getLogger(__name__)


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


def print_image(image: Image.Image, printer_name: str = None):
    """PIL 이미지를 Windows 프린터로 직접 출력한다."""
    printer_name = printer_name or config.PRINTER_NAME

    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)

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
