import logging
import os
import shutil
import tempfile
import zipfile

from PIL import Image

import config

logger = logging.getLogger(__name__)


def process_file(file_path: str):
    """파일 처리 → 출력 모드에 따라 분기 → done/error 이동."""
    os.makedirs(config.DONE_DIR, exist_ok=True)
    os.makedirs(config.ERROR_DIR, exist_ok=True)

    filename = os.path.basename(file_path)

    try:
        images = _load_images(file_path)
        if not images:
            raise RuntimeError(f"출력할 이미지가 없습니다: {filename}")

        if config.PRINTER_MODE == "gtx4cmd":
            _print_via_gtx4cmd(images)
        else:
            _print_via_direct(images)

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


def _print_via_direct(images: list[Image.Image]):
    """win32print 직접 출력. 가먼트 잉크 과소비 방지를 위해 흰 배경 평탄화."""
    from printer import print_image

    for i, img in enumerate(images, 1):
        logger.info("  페이지 %d/%d 출력 중...", i, len(images))
        print_image(_flatten_to_white(img))


def _print_via_gtx4cmd(images: list[Image.Image]):
    """GTX4CMD.exe 경유 출력 (PNG만 지원)."""
    from gtx4cmd import create_arx4, send_to_printer
    from xml_builder import build_xml

    tmp_dir = tempfile.mkdtemp(prefix="gtx4_")
    try:
        xml_path = os.path.join(tmp_dir, "settings.xml")
        build_xml(xml_path)

        platen_w, platen_h = config.PLATEN_DIMS.get(
            config.PLATEN_SIZE, config.PLATEN_DIMS[0]
        )
        manual_size = config.SIZE or None

        for i, img in enumerate(images):
            png_path = os.path.join(tmp_dir, f"page_{i}.png")
            arx4_path = os.path.join(tmp_dir, f"page_{i}.arx4")

            _flatten_to_white(img).save(png_path, "PNG")

            # SIZE 명시 시 그 값 우선, 아니면 수동 MAGNIFICATION, 아니면 원본 크기
            base_w, base_h = _image_dims_mm10(img)
            if manual_size:
                size = manual_size
                magnification = None
                eff_w, eff_h = _parse_size(manual_size, base_w, base_h)
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
                "  배치 — 이미지 %dx%d (0.1mm), 플래튼 %dx%d, 위치 %s",
                eff_w, eff_h, platen_w, platen_h,
                position or config.POSITION,
            )

            logger.info("  페이지 %d/%d ARX4 생성 중...", i + 1, len(images))
            rc = create_arx4(
                xml_path, png_path, arx4_path,
                position=position,
                size=size, magnification=magnification, white=config.WHITE_AS,
            )
            if rc != 0:
                raise RuntimeError(f"ARX4 생성 실패 (코드: {rc})")

            logger.info("  페이지 %d/%d 프린터 전송 중...", i + 1, len(images))
            rc = send_to_printer(arx4_path)
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


def _flatten_to_white(img: Image.Image) -> Image.Image:
    """RGBA 알파 이진화(임계 128) 후 배경을 정확한 RGB(255,255,255)로 합성.

    GTX4CMD의 `-W 0`(기본)은 정확한 RGB(255,255,255) 픽셀만 투명으로 해석하므로,
    안티앨리어싱/렌더 오차로 '거의 흰색'이 된 배경 픽셀이 잉크로 분사되는 것을 막는다.
    """
    if img.mode != "RGBA":
        return img.convert("RGB")
    alpha = img.split()[3]
    mask = alpha.point(lambda a: 255 if a >= 128 else 0)
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img.convert("RGB"), mask=mask)
    return flat


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
