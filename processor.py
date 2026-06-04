import logging
import os
import shutil
import tempfile
import time
import zipfile

from PIL import Image, ImageChops

import config

logger = logging.getLogger(__name__)


def process_file(file_path: str, printer_name: str | None = None, needs_plate_change: bool = False):
    """파일 처리 → 출력 모드에 따라 분기 → done/error 이동.

    printer_name: 다중 프린터 분배기에서 미리 결정한 대상 프린터. None이면 config.PRINTER_NAME 사용.
    needs_plate_change: 주문서 플레이트 교체 대상(아동용 등). True면 아동 플레이트(10x12)로 출력.
    """
    os.makedirs(config.DONE_DIR, exist_ok=True)
    os.makedirs(config.ERROR_DIR, exist_ok=True)

    filename = os.path.basename(file_path)
    target_printer = printer_name or config.PRINTER_NAME

    try:
        images = _load_images(file_path)
        if not images:
            raise RuntimeError(f"출력할 이미지가 없습니다: {filename}")

        if config.PRINTER_MODE == "cli":
            _print_via_cli(images, target_printer, needs_plate_change)
        else:
            _print_via_direct(images, target_printer)

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
        # 호출자(agent.py)가 실패를 인지하고 mark_failed 를 서버에 보낼 수 있도록 재던지기.
        # 이전에는 swallow 하여 "처리 실패" 로그 후에도 호출자가 정상 완료로 인지,
        # API DLL 누락 같은 출력 실패가 서버에 PRINTED 로 잘못 기록되는 문제가 있었음.
        raise


def _load_images(file_path: str) -> list[Image.Image]:
    """파일 타입에 따라 PIL Image 리스트로 변환.

    - PDF: pdf2image로 변환
    - PNG/JPG: 직접 로드
    - ZIP: 내부 이미지 파일 추출
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _load_from_pdf(file_path)
    elif ext == ".png" or ext == ".jpg" or ext == ".jpeg":
        return [Image.open(file_path).copy()]
    elif ext == ".zip":
        return _load_from_zip(file_path)
    else:
        raise RuntimeError(f"지원하지 않는 파일 형식: {ext}")


def _load_from_pdf(file_path: str) -> list[Image.Image]:
    """PDF → PIL Image 리스트 (투명 배경 보존)."""
    from pdf2image import convert_from_path

    return convert_from_path(
        file_path,
        dpi=config.RENDER_DPI,
        poppler_path=config.POPPLER_PATH,
        transparent=True,
        use_pdftocairo=True,
    )


def _load_from_zip(file_path: str) -> list[Image.Image]:
    """ZIP 내부의 이미지 파일(PNG/JPG)을 추출하여 PIL Image 리스트로 반환."""
    images = []
    tmp_dir = tempfile.mkdtemp(prefix="zip_")
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            zf.extractall(tmp_dir)

        image_exts = {".png", ".jpg", ".jpeg"}
        for root, _, files in os.walk(tmp_dir):
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in image_exts:
                    img_path = os.path.join(root, name)
                    images.append(Image.open(img_path).copy())
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return images


def _print_via_direct(images: list[Image.Image], printer_name: str):
    """win32print 직접 출력. 가먼트 잉크 과소비 방지를 위해 흰 배경 평탄화."""
    from printer import print_image

    for i, img in enumerate(images, 1):
        logger.info("  페이지 %d/%d 출력 중 (%s)...", i, len(images), printer_name)
        print_image(_flatten_to_white(img), printer_name)


def _print_via_cli(images: list[Image.Image], printer_name: str, needs_plate_change: bool = False):
    """가먼트 CLI 경유 출력 (PNG만 지원).

    needs_plate_change=True 면 아동 플레이트(10x12), 아니면 성인 플레이트(14x16) 사용.
    AUTO_FIT 모드(기본): 이미지를 플레이트에 contain(축소만, 작으면 원본), 가로 중앙·세로 상단 배치.
    """
    from garment_cli import (
        create_arx4,
        describe_cli_selection,
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

        # 플레이트 선택: 아동(플레이트 교체) → 10x12, 성인(기본) → 14x16
        platen_idx = config.PLATEN_CHILD if needs_plate_change else config.PLATEN_ADULT
        platen_w, platen_h = config.PLATEN_DIMS.get(platen_idx, config.PLATEN_DIMS[0])
        platen_label = "아동" if needs_plate_change else "성인"

        manual_size = config.SIZE or None
        data_ext = preferred_data_extension(printer_name)
        target_model = "pro" if data_ext == ".arxp" else "legacy"
        xml_path = os.path.join(tmp_dir, "settings.xml")
        build_xml(
            xml_path,
            platen_size=platen_idx,  # byPlatenSize 를 선택 플레이트와 동기화
            target_model=target_model,
            include_machine_mode=target_model != "pro",
        )

        for i, img in enumerate(images):
            png_path = os.path.join(tmp_dir, f"page_{i}.png")
            arx4_path = os.path.join(tmp_dir, f"page_{i}{data_ext}")

            flat_img = _flatten_to_white(img)
            flat_img.save(png_path, "PNG", dpi=(config.RENDER_DPI, config.RENDER_DPI))

            base_w, base_h = _image_dims_mm10(img)
            non_white_pixels, non_white_bbox = _non_white_stats(flat_img)
            if config.AUTO_FIT and not manual_size:
                # GTXpro는 DPI 없는 PNG + -R 조합에서 기본 DPI 해석이 달라질 수 있다.
                # AUTO_FIT은 0.1mm 절대 크기(-S)로 넘겨 API의 DPI 추정에 의존하지 않는다.
                scale = min(platen_w / max(1, base_w), platen_h / max(1, base_h), 1.0)
                eff_w, eff_h = int(round(base_w * scale)), int(round(base_h * scale))
                size = f"{eff_w:04d}{eff_h:04d}"
                magnification = None
                position = _calc_fit_position(eff_w, eff_h, platen_w, platen_h)
            elif manual_size:
                # SIZE 수동 지정 우선
                size = manual_size
                magnification = None
                eff_w, eff_h = _parse_size(manual_size, base_w, base_h)
                position = (
                    _calc_center_position(eff_w, eff_h, platen_w, platen_h)
                    if config.AUTO_CENTER else None
                )
            else:
                # 수동 MAGNIFICATION 또는 원본 크기 + (옵션) 중앙 정렬
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
            logger.info(
                "  이미지 진단 — dpi=%s, nonWhite=%d, bbox=%s",
                img.info.get("dpi") or f"default:{config.RENDER_DPI}",
                non_white_pixels,
                non_white_bbox or "-",
            )

            logger.info("  페이지 %d/%d 인쇄 데이터 생성 중 (%s)...", i + 1, len(images), data_ext)
            rc = create_arx4(
                xml_path, png_path, arx4_path,
                position=position,
                size=size, magnification=magnification, white=config.WHITE_AS,
                printer_name=printer_name,
            )
            if rc != 0:
                raise RuntimeError(f"인쇄 데이터 생성 실패 (코드: {rc})")

            _extract_arx_diagnostic(
                extract_data=extract_data,
                arx_path=arx4_path,
                page=i,
                data_ext=data_ext,
                printer_name=printer_name,
            )

            logger.info("  페이지 %d/%d 프린터 전송 중 (%s)...", i + 1, len(images), printer_name)
            rc = send_to_printer(arx4_path, printer_name)
            if rc != 0:
                raise RuntimeError(f"프린터 전송 실패 (코드: {rc})")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _image_dims_mm10(img: Image.Image) -> tuple[int, int]:
    """PIL Image의 픽셀 + DPI 메타데이터 → 0.1mm 단위 (W, H)."""
    dpi = img.info.get("dpi") or (config.RENDER_DPI, config.RENDER_DPI)
    dpi_x, dpi_y = dpi if isinstance(dpi, tuple) else (dpi, dpi)
    dpi_x = dpi_x or config.RENDER_DPI
    dpi_y = dpi_y or config.RENDER_DPI
    w = int(round(img.width / dpi_x * 254))
    h = int(round(img.height / dpi_y * 254))
    return w, h


def _parse_size(size_str: str, fallback_w: int, fallback_h: int) -> tuple[int, int]:
    """8자리 SIZE 문자열 → (W, H) 0.1mm. 형식 오류 시 fallback."""
    if size_str and len(size_str) == 8 and size_str.isdigit():
        return int(size_str[:4]), int(size_str[4:])
    return fallback_w, fallback_h


def _calc_center_position(img_w: int, img_h: int, platen_w: int, platen_h: int) -> str:
    """이미지/플래튼 0.1mm 기준 중앙 정렬 -L 8자리 문자열."""
    left = max(0, min(9999, (platen_w - img_w) // 2))
    top = max(0, min(9999, (platen_h - img_h) // 2))
    return f"{left:04d}{top:04d}"


def _calc_fit_position(img_w: int, img_h: int, platen_w: int, platen_h: int) -> str:
    """플레이트 맞춤 정렬 — 가로(너비)는 중앙, 세로(높이)는 상단. -L 8자리 문자열."""
    left = max(0, min(9999, (platen_w - img_w) // 2))
    top = 0
    return f"{left:04d}{top:04d}"


def _flatten_to_white(img: Image.Image) -> Image.Image:
    """RGBA 알파 이진화(임계 128) 후 배경을 정확한 RGB(255,255,255)로 합성.

    가먼트 CLI의 `-W 0`(기본)은 정확한 RGB(255,255,255) 픽셀만 투명으로 해석하므로,
    안티앨리어싱/렌더 오차로 '거의 흰색'이 된 배경 픽셀이 잉크로 분사되는 것을 막는다.
    """
    if img.mode != "RGBA":
        return img.convert("RGB")
    alpha = img.split()[3]
    mask = alpha.point(lambda a: 255 if a >= 128 else 0)
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img.convert("RGB"), mask=mask)
    return flat


def _non_white_stats(img: Image.Image) -> tuple[int, tuple[int, int, int, int] | None]:
    """RGB(255,255,255)가 아닌 픽셀 수와 bounding box."""
    rgb = img.convert("RGB")
    white = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, white)
    bbox = diff.getbbox()
    if bbox is None:
        return 0, None
    mask = diff.convert("L").point(lambda v: 255 if v else 0)
    count = mask.histogram()[255]
    return count, bbox


def _extract_arx_diagnostic(extract_data, arx_path: str, page: int, data_ext: str, printer_name: str) -> None:
    """생성된 ARX/ARXP 내부 이미지와 XML을 진단 폴더에 추출한다."""
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
    """동일 파일명 충돌 시 번호를 붙여 고유 경로 반환."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while True:
        candidate = f"{base}_{n}{ext}"
        if not os.path.exists(candidate):
            return candidate
        n += 1
