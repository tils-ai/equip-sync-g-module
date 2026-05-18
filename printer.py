import logging

import win32print
import win32ui
from PIL import Image, ImageWin

import config

logger = logging.getLogger(__name__)


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
