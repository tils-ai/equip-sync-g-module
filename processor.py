import logging
import os
import shutil
import tempfile
import time

from PIL import Image

import config

logger = logging.getLogger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def process_file(
    file_path: str,
    printer_name: str | None = None,
    needs_plate_change: bool = False,
    ink: int | None = None,
):
    os.makedirs(config.DONE_DIR, exist_ok=True)
    os.makedirs(config.ERROR_DIR, exist_ok=True)

    filename = os.path.basename(file_path)
    target_printer = printer_name or config.PRINTER_NAME

    try:
        _ensure_png(file_path)

        if config.PRINTER_MODE == "cli":
            _print_via_cli(file_path, target_printer, needs_plate_change, ink)
        else:
            _print_via_direct(file_path, target_printer)

        dest = _unique_path(os.path.join(config.DONE_DIR, filename))
        shutil.move(file_path, dest)
        logger.info("완료 → %s", os.path.basename(dest))

    except Exception:
        logger.exception("처리 실패: %s", filename)
        dest = _unique_path(os.path.join(config.ERROR_DIR, filename))
        try:
            shutil.move(file_path, dest)
        except Exception:
            logger.exception("에러 폴더 이동 실패: %s", filename)
        raise


def _ensure_png(file_path: str) -> None:
    with open(file_path, "rb") as f:
        head = f.read(len(PNG_SIGNATURE))
    if head != PNG_SIGNATURE:
        raise RuntimeError(f"PNG 파일이 아닙니다 (PNG 만 출력합니다): {os.path.basename(file_path)}")


def _print_via_direct(png_path: str, printer_name: str):
    from printer import print_image

    logger.info("  직접 출력 중 (%s)...", printer_name)
    with Image.open(png_path) as img:
        print_image(img, printer_name)


def _print_via_cli(
    png_path: str,
    printer_name: str,
    needs_plate_change: bool = False,
    ink: int | None = None,
):
    from garment_cli import (
        api_backend_active,
        create_arx4,
        describe_cli_selection,
        describe_versions,
        extract_data,
        preferred_data_extension,
        printer_driver_summary,
        send_to_printer,
    )
    from xml_builder import build_xml

    tmp_dir = tempfile.mkdtemp(prefix="garment_")
    try:
        logger.info("  가먼트 실행 설정: %s", describe_cli_selection(printer_name))
        logger.info("  가먼트 프린터 드라이버: %s", printer_driver_summary(printer_name))
        logger.info("  가먼트 버전 조합: %s", describe_versions(printer_name))

        platen_idx = config.PLATEN_CHILD if needs_plate_change else config.PLATEN_ADULT
        platen_w, platen_h = config.PLATEN_DIMS.get(platen_idx, config.PLATEN_DIMS[0])
        platen_label = "아동" if needs_plate_change else "성인"

        manual_size = config.SIZE or None
        data_ext = preferred_data_extension(printer_name)
        target_model = "pro" if data_ext == ".arxp" else "legacy"
        xml_path = os.path.join(tmp_dir, "settings.xml")
        xml_overrides = {}
        if ink is not None:
            xml_overrides["ink"] = int(ink)
            logger.info("  잉크 모드 오버라이드: %s", "Color+White(컬러옷)" if int(ink) == 2 else f"ink={ink}")
        build_xml(
            xml_path,
            platen_size=platen_idx,
            target_model=target_model,
            include_machine_mode=target_model != "pro",
            **xml_overrides,
        )

        arx4_path = os.path.join(tmp_dir, f"print{data_ext}")

        with Image.open(png_path) as img:
            base_w, base_h = _image_dims_mm10(img)
            img_dpi = img.info.get("dpi")

        if config.AUTO_FIT and not manual_size:
            scale = min(platen_w / max(1, base_w), platen_h / max(1, base_h), 1.0)
            eff_w, eff_h = int(round(base_w * scale)), int(round(base_h * scale))
            size = f"{eff_w:04d}{eff_h:04d}"
            magnification = None
            position = _calc_fit_position(eff_w, eff_h, platen_w, platen_h)
        elif manual_size:
            size = manual_size
            magnification = None
            eff_w, eff_h = _parse_size(manual_size, base_w, base_h)
            position = (
                _calc_center_position(eff_w, eff_h, platen_w, platen_h)
                if config.AUTO_CENTER else None
            )
        else:
            size = None
            magnification = config.MAGNIFICATION or None
            if magnification:
                mag = int(magnification) / 1000.0
                eff_w, eff_h = int(round(base_w * mag)), int(round(base_h * mag))
            else:
                eff_w, eff_h = base_w, base_h
            position = (
                _calc_center_position(eff_w, eff_h, platen_w, platen_h)
                if config.AUTO_CENTER else None
            )

        logger.info(
            "  배치 — %s 플레이트 %dx%d, 이미지 %dx%d (0.1mm), 위치 %s, size=%s, mag=%s",
            platen_label, platen_w, platen_h, eff_w, eff_h,
            position or config.POSITION, size or "-", magnification or "-",
        )
        logger.info("  이미지 — dpi=%s", img_dpi or f"기본값:{config.RENDER_DPI}")

        logger.info("  인쇄 데이터 생성 중 (%s)...", data_ext)
        rc = create_arx4(
            xml_path, png_path, arx4_path,
            position=position,
            size=size, magnification=magnification, white=config.WHITE_AS,
            printer_name=printer_name,
            option_overrides={**xml_overrides, "platen_size": platen_idx},
        )
        if rc != 0:
            raise RuntimeError(f"인쇄 데이터 생성 실패 (코드: {rc})")

        if api_backend_active(printer_name):
            logger.info("  인쇄 데이터 추출 진단 건너뜀 (직접 호출 경로)")
        else:
            _extract_arx_diagnostic(
                extract_data=extract_data,
                arx_path=arx4_path,
                page=0,
                data_ext=data_ext,
                printer_name=printer_name,
            )

        logger.info("  프린터 전송 중 (%s)...", printer_name)
        rc = send_to_printer(arx4_path, printer_name)
        if rc != 0:
            raise RuntimeError(f"프린터 전송 실패 (코드: {rc})")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _image_dims_mm10(img: Image.Image) -> tuple[int, int]:
    dpi = img.info.get("dpi") or (config.RENDER_DPI, config.RENDER_DPI)
    dpi_x, dpi_y = dpi if isinstance(dpi, tuple) else (dpi, dpi)
    dpi_x = dpi_x or config.RENDER_DPI
    dpi_y = dpi_y or config.RENDER_DPI
    w = int(round(img.width / dpi_x * 254))
    h = int(round(img.height / dpi_y * 254))
    return w, h


def _parse_size(size_str: str, fallback_w: int, fallback_h: int) -> tuple[int, int]:
    if size_str and len(size_str) == 8 and size_str.isdigit():
        return int(size_str[:4]), int(size_str[4:])
    return fallback_w, fallback_h


def _calc_center_position(img_w: int, img_h: int, platen_w: int, platen_h: int) -> str:
    left = max(0, min(9999, (platen_w - img_w) // 2))
    top = max(0, min(9999, (platen_h - img_h) // 2))
    return f"{left:04d}{top:04d}"


def _calc_fit_position(img_w: int, img_h: int, platen_w: int, platen_h: int) -> str:
    left = max(0, min(9999, (platen_w - img_w) // 2))
    top = 0
    return f"{left:04d}{top:04d}"


def _extract_arx_diagnostic(extract_data, arx_path: str, page: int, data_ext: str, printer_name: str) -> None:
    diag_dir = os.path.join(os.path.dirname(config.LOG_FILE), "diagnostics")
    os.makedirs(diag_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stem = f"garment-extract-{stamp}-p{page + 1}"
    arx_copy = os.path.join(diag_dir, f"{stem}{data_ext}")
    xml_out = os.path.join(diag_dir, f"{stem}.xml")
    img_out = os.path.join(diag_dir, f"{stem}.png")
    try:
        shutil.copy2(arx_path, arx_copy)
    except OSError as e:
        logger.warning("  인쇄 데이터 진단 원본 복사 실패: %s", e)
    rc = extract_data(
        arx_path,
        xml_path=xml_out,
        image_path=img_out,
        printer_name=printer_name,
    )
    if rc == 0:
        logger.info("  인쇄 데이터 추출 진단 저장: %s, %s, %s", arx_copy, xml_out, img_out)
    else:
        logger.warning("  인쇄 데이터 추출 진단 실패 (%s, rc=%s)", data_ext, rc)


def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while True:
        candidate = f"{base}_{n}{ext}"
        if not os.path.exists(candidate):
            return candidate
        n += 1
