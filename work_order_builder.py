"""작업지시서 PDF 생성 — reportlab 기반.

dps-store/entities/print/pdf/work-order-pdf.ts(브라우저 다운로드용)와 동일한 A4 1장 레이아웃을
가먼트 클라이언트(Python) 측에서 재현한다.

레이아웃 사양(웹 기준 96 DPI px → reportlab pt 환산):
- A4 595×842pt, 외곽 패딩 36pt(웹 48px)
- 워터마크 4방향(상/하/좌/우), 8.25pt(11px), #dc2626
- 제목 24pt(32px) bold, 상단 구분선 2pt
- 정보표: 라벨 칸 90pt(120px), 폰트 12pt(16px), 라벨 배경 #f5f5f5, 테두리 1pt #ddd
- 비고 행 90pt(120px) 높이
- 미리보기 135×135pt(180×180px) contain + #ddd 테두리 + #fafafa 배경 + "미리보기" 라벨
- QR 112.5×112.5pt(150×150px) + "작업 상세" 라벨
- 푸터 9pt(12px) #888 생성일시
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkOrderJob:
    order_number: str
    product_name: str
    option_name: Optional[str]
    quantity: int
    wepnp_seqno: str
    tenant_name: str
    brand_name: str
    printed_by: str
    work_url: str
    item_index: int = 1
    item_total: int = 1
    preview_image_path: Optional[str] = None
    design_filename: Optional[str] = None
    printer_name: Optional[str] = None


def format_order_number(order_number: str, item_index: int, item_total: int) -> str:
    """주문번호 표시 형식: 20261211-000001-01(3)"""
    total = item_total if item_total and item_total > 0 else 1
    return f"{order_number}-{item_index:02d}({total})"


def _font_path(name: str) -> Optional[str]:
    """assets/fonts/<name> 경로 (frozen 환경에서도 동작)."""
    import sys

    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / "fonts" / name)
        candidates.append(Path(sys.executable).parent / "assets" / "fonts" / name)
    candidates.append(Path(__file__).parent / "assets" / "fonts" / name)

    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _register_fonts() -> tuple[str, str]:
    """한글 폰트 등록. 반환: (regular_name, bold_name)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    regular = _font_path("Pretendard-Regular.ttf")
    bold = _font_path("Pretendard-Bold.ttf")
    if regular and bold:
        try:
            pdfmetrics.registerFont(TTFont("Pretendard", regular))
            pdfmetrics.registerFont(TTFont("Pretendard-Bold", bold))
            return "Pretendard", "Pretendard-Bold"
        except Exception:
            logger.exception("Pretendard ttf 등록 실패 — CID 폴백")

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
        return "HYSMyeongJo-Medium", "HYGothic-Medium"
    except Exception:
        logger.exception("CIDFont 등록 실패 — Helvetica 폴백 (한글 미지원)")
        return "Helvetica", "Helvetica-Bold"


def _make_qr(url: str):
    """QR 코드 PIL Image 생성."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _draw_watermark(c, page_w, page_h, pad, regular_font, bold_font, left, mid, right):
    """사방 워터마크 — 상/하 가로, 좌/우 90도 회전."""
    from reportlab.lib.colors import HexColor

    wm_size = 8.25  # 웹 11px
    inner_h = page_h - pad * 2
    half_len = inner_h / 2
    color = HexColor("#dc2626")

    c.saveState()
    c.setFillColor(color)

    # 상단/하단
    for y in (page_h - 6 - wm_size, 6):
        c.setFont(regular_font, wm_size)
        c.drawString(pad, y, left)
        c.setFont(bold_font, wm_size)
        c.drawCentredString(page_w / 2, y, mid)
        c.setFont(regular_font, wm_size)
        c.drawRightString(page_w - pad, y, right)

    # 좌측 (90도 회전)
    c.saveState()
    c.translate(9 + wm_size, page_h / 2)
    c.rotate(90)
    c.setFont(regular_font, wm_size)
    c.drawString(-half_len, 0, left)
    c.setFont(bold_font, wm_size)
    c.drawCentredString(0, 0, mid)
    c.setFont(regular_font, wm_size)
    c.drawRightString(half_len, 0, right)
    c.restoreState()

    # 우측 (-90도)
    c.saveState()
    c.translate(page_w - 9 - wm_size, page_h / 2)
    c.rotate(-90)
    c.setFont(regular_font, wm_size)
    c.drawString(-half_len, 0, left)
    c.setFont(bold_font, wm_size)
    c.drawCentredString(0, 0, mid)
    c.setFont(regular_font, wm_size)
    c.drawRightString(half_len, 0, right)
    c.restoreState()

    c.restoreState()


def _draw_info_table(c, inner_x, inner_w, table_top, regular_font, bold_font, rows, note_height):
    """정보 표 — 라벨 칸 회색 배경 + 1pt #ddd 테두리. 마지막에 비고 행 추가.

    반환: 비고 행 하단 y 좌표.
    """
    from reportlab.lib.colors import HexColor

    table_font = 12  # 웹 16px
    label_w = 90    # 웹 120px
    cell_pad_x = 12
    cell_pad_y = 9
    row_h = table_font + cell_pad_y * 2  # 30pt

    border_color = HexColor("#dddddd")
    label_bg = HexColor("#f5f5f5")
    text_color = (0, 0, 0)

    def _draw_row(y_bottom, height, label, value, value_is_mono=False):
        # 라벨 셀 배경
        c.setFillColor(label_bg)
        c.rect(inner_x, y_bottom, label_w, height, stroke=0, fill=1)
        # 테두리 (라벨/값 셀 각각)
        c.setStrokeColor(border_color)
        c.setLineWidth(1)
        c.rect(inner_x, y_bottom, label_w, height, stroke=1, fill=0)
        c.rect(inner_x + label_w, y_bottom, inner_w - label_w, height, stroke=1, fill=0)
        # 라벨 텍스트 (셀 상단 정렬: 비고만 위 정렬, 그 외엔 세로 중앙)
        c.setFillColorRGB(*text_color)
        c.setFont(bold_font, table_font)
        if height > row_h:
            # 비고 행 — vertical-align: top
            label_y = y_bottom + height - cell_pad_y - table_font
        else:
            label_y = y_bottom + (height - table_font) / 2 + table_font * 0.25
        c.drawString(inner_x + cell_pad_x, label_y, label)
        # 값 텍스트
        if value:
            value_font_size = 10.5 if value_is_mono else table_font
            c.setFont(regular_font, value_font_size)
            value_y = y_bottom + (height - value_font_size) / 2 + value_font_size * 0.25 \
                if height <= row_h else y_bottom + height - cell_pad_y - value_font_size
            # 셀 폭에 맞춰 단순 절단
            avail_w = inner_w - label_w - cell_pad_x * 2
            max_chars = int(avail_w / (value_font_size * 0.6)) or 1
            display = value if len(value) <= max_chars else value[: max_chars - 1] + "…"
            c.drawString(inner_x + label_w + cell_pad_x, value_y, display)

    current_y = table_top
    for label, value, is_mono in rows:
        row_y = current_y - row_h
        _draw_row(row_y, row_h, label, value, is_mono)
        current_y = row_y

    # 비고 행 (높이 = note_height + 패딩)
    note_total_h = note_height + cell_pad_y * 2
    note_y = current_y - note_total_h
    _draw_row(note_y, note_total_h, "비고", "")
    return note_y


def build_work_order_pdf(job: WorkOrderJob, dest_path: str) -> str:
    """A4 1장 작업지시서 PDF — 웹 다운로드와 동일 레이아웃."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    regular_font, bold_font = _register_fonts()

    page_w, page_h = A4
    c = canvas.Canvas(dest_path, pagesize=A4)
    c.setTitle(f"작업지시서_{job.order_number}_{job.wepnp_seqno}")

    pad = 36  # 웹 48px
    inner_x = pad
    inner_y = pad
    inner_w = page_w - pad * 2
    inner_h = page_h - pad * 2

    # 워터마크
    _draw_watermark(
        c,
        page_w,
        page_h,
        pad,
        regular_font,
        bold_font,
        left=f"{job.brand_name} | {job.tenant_name} | {job.printed_by}",
        mid="⚠ 작업 후 파기 ⚠",
        right=job.work_url,
    )

    # 제목
    title_size = 24  # 웹 32px
    title_y = inner_y + inner_h - title_size
    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold_font, title_size)
    c.drawCentredString(page_w / 2, title_y, "작업지시서")

    # 구분선 (제목 margin-bottom 18pt = 웹 24px)
    sep_y = title_y - 18
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(2)
    c.line(inner_x, sep_y, inner_x + inner_w, sep_y)

    # 정보 표
    table_top = sep_y - 18  # 구분선 margin-bottom 18pt
    rows: list[tuple[str, str, bool]] = []
    rows.append(("주문번호", format_order_number(job.order_number, job.item_index, job.item_total), False))
    rows.append(("상품명", job.product_name, False))
    if job.option_name:
        rows.append(("옵션", job.option_name, False))
    rows.append(("수량", f"{job.quantity}개", False))
    rows.append(("편집번호", job.wepnp_seqno, False))
    if job.design_filename:
        rows.append(("디자인 파일", job.design_filename, True))
    if job.printer_name:
        rows.append(("출력 장비", job.printer_name, False))

    table_bottom_y = _draw_info_table(
        c, inner_x, inner_w, table_top, regular_font, bold_font, rows, note_height=90
    )

    # 푸터 (생성일시)
    footer_size = 9  # 웹 12px
    footer_y = inner_y + footer_size
    c.setFillColor(HexColor("#888888"))
    c.setFont(regular_font, footer_size)
    c.drawCentredString(
        page_w / 2, footer_y, f"생성일시: {datetime.now().strftime('%Y. %m. %d. %H:%M:%S')}"
    )

    # 미리보기 + QR (테이블 ~ 푸터 사이를 하단 정렬)
    block_bottom = footer_y + footer_size + 9  # 푸터 margin-top 12pt → footer 위 약 9pt 여유
    block_top = table_bottom_y - 9

    has_preview = bool(job.preview_image_path and os.path.exists(job.preview_image_path))
    preview_size = 135  # 웹 180px
    qr_size = 112.5     # 웹 150px
    label_gap = 6        # 라벨 위 gap (웹 8px)
    label_h = 9
    block_gap = 12       # 미리보기 묶음 ↔ QR 묶음 사이 (웹 16px)

    if has_preview:
        total_h = preview_size + label_gap + label_h + block_gap + qr_size + label_gap + label_h
    else:
        total_h = qr_size + label_gap + label_h

    available_h = block_top - block_bottom
    block_origin = block_bottom + max(0, available_h - total_h)

    border_color = HexColor("#dddddd")
    bg_color = HexColor("#fafafa")
    label_color = HexColor("#666666")

    if has_preview:
        preview_y = block_origin + total_h - preview_size
        preview_x = (page_w - preview_size) / 2
        # 배경
        c.setFillColor(bg_color)
        c.rect(preview_x, preview_y, preview_size, preview_size, stroke=0, fill=1)
        # 이미지 (contain)
        try:
            img_reader = ImageReader(job.preview_image_path)
            iw, ih = img_reader.getSize()
            scale = min(preview_size / iw, preview_size / ih)
            draw_w = iw * scale
            draw_h = ih * scale
            draw_x = preview_x + (preview_size - draw_w) / 2
            draw_y = preview_y + (preview_size - draw_h) / 2
            c.drawImage(img_reader, draw_x, draw_y, width=draw_w, height=draw_h, mask="auto")
        except Exception:
            logger.exception("미리보기 이미지 삽입 실패")
        # 테두리
        c.setStrokeColor(border_color)
        c.setLineWidth(1)
        c.rect(preview_x, preview_y, preview_size, preview_size, stroke=1, fill=0)
        # 라벨
        c.setFillColor(label_color)
        c.setFont(regular_font, label_h)
        c.drawCentredString(page_w / 2, preview_y - label_gap - label_h * 0.8, "미리보기")

        qr_y = preview_y - label_gap - label_h - block_gap - qr_size
    else:
        qr_y = block_origin + total_h - qr_size

    # QR
    try:
        qr_img = _make_qr(job.work_url)
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        qr_x = (page_w - qr_size) / 2
        c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)
        c.setFillColor(label_color)
        c.setFont(regular_font, label_h)
        c.drawCentredString(page_w / 2, qr_y - label_gap - label_h * 0.8, "작업 상세")
    except Exception:
        logger.exception("QR 생성 실패 — QR 생략하고 진행")

    c.showPage()
    c.save()
    logger.info("작업지시서 PDF 생성: %s", dest_path)
    return dest_path
