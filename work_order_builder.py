"""작업지시서 PDF 생성 — reportlab 기반.

기존 dps-store/entities/print/pdf/work-order-pdf.ts (브라우저용 html-to-image+jspdf)의
서버 출력자/QR/워터마크 레이아웃을 가먼트 클라이언트(Python) 측에서 재구현한다.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
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
    item_index: int = 1  # 주문 내 디자인 순번 (1-based)
    item_total: int = 1  # 주문 내 총 디자인 수
    preview_image_path: Optional[str] = None  # 다운로드한 디자인 PNG 경로


def format_order_number(order_number: str, item_index: int, item_total: int) -> str:
    """주문번호 표시 형식: 20261211-000001-01(3)"""
    total = item_total if item_total and item_total > 0 else 1
    return f"{order_number}-{item_index:02d}({total})"


def _font_path(name: str) -> Optional[str]:
    """assets/fonts/<name>.otf 경로 (frozen 환경에서도 동작)."""
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
    """한글 폰트 등록. 반환: (regular_name, bold_name).

    1순위: Pretendard .ttf (assets/fonts/, 있을 경우)
    2순위: reportlab 내장 한국어 CIDFont(HYSMyeongJo-Medium / HYGothic-Medium)
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    # 1) 번들 ttf 우선 (otf는 reportlab 미지원이라 ttf만)
    regular = _font_path("Pretendard-Regular.ttf")
    bold = _font_path("Pretendard-Bold.ttf")
    if regular and bold:
        try:
            pdfmetrics.registerFont(TTFont("Pretendard", regular))
            pdfmetrics.registerFont(TTFont("Pretendard-Bold", bold))
            return "Pretendard", "Pretendard-Bold"
        except Exception:
            logger.exception("Pretendard ttf 등록 실패 — CID 폴백")

    # 2) reportlab 내장 한국어 CIDFont
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
        return "HYSMyeongJo-Medium", "HYGothic-Medium"
    except Exception:
        logger.exception("CIDFont 등록 실패 — Helvetica 폴백 (한글 미지원)")
        return "Helvetica", "Helvetica-Bold"


def _make_qr(url: str, size_mm: float = 25):
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


def build_work_order_pdf(job: WorkOrderJob, dest_path: str) -> str:
    """A4 1장짜리 작업지시서 PDF를 생성하여 dest_path에 저장. 경로 반환."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    regular_font, bold_font = _register_fonts()

    page_w, page_h = A4
    c = canvas.Canvas(dest_path, pagesize=A4)
    c.setTitle(f"작업지시서_{job.order_number}_{job.wepnp_seqno}")

    # ── 워터마크 (사방 테두리) ──
    watermark_text = f"{job.brand_name} | {job.tenant_name} | {job.printed_by}    ⚠ 작업 후 파기 ⚠"
    c.saveState()
    c.setFont(regular_font, 8)
    c.setFillColorRGB(0.85, 0.2, 0.2)
    # 상단/하단
    c.drawCentredString(page_w / 2, page_h - 8 * mm, watermark_text)
    c.drawCentredString(page_w / 2, 5 * mm, watermark_text)
    # 좌측 (90도 회전)
    c.saveState()
    c.translate(8 * mm, page_h / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, watermark_text)
    c.restoreState()
    # 우측 (-90도 회전)
    c.saveState()
    c.translate(page_w - 8 * mm, page_h / 2)
    c.rotate(-90)
    c.drawCentredString(0, 0, watermark_text)
    c.restoreState()
    c.restoreState()

    # ── 본문 영역 (테두리 안쪽 12mm 마진) ──
    margin = 16 * mm
    inner_x = margin
    inner_y = margin
    inner_w = page_w - margin * 2
    inner_h = page_h - margin * 2

    # 제목
    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold_font, 20)
    c.drawString(inner_x, inner_y + inner_h - 24, "작업지시서")
    c.setFont(regular_font, 10)
    c.drawString(
        inner_x,
        inner_y + inner_h - 40,
        f"주문번호 · {format_order_number(job.order_number, job.item_index, job.item_total)}",
    )

    # QR 코드 (우측 상단)
    try:
        qr_img = _make_qr(job.work_url)
        qr_size = 28 * mm
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        from reportlab.lib.utils import ImageReader

        c.drawImage(
            ImageReader(qr_buf),
            inner_x + inner_w - qr_size,
            inner_y + inner_h - qr_size - 4,
            width=qr_size,
            height=qr_size,
        )
        c.setFont(regular_font, 8)
        c.drawCentredString(
            inner_x + inner_w - qr_size / 2,
            inner_y + inner_h - qr_size - 14,
            "작업 페이지",
        )
    except Exception:
        logger.exception("QR 생성 실패 — QR 생략하고 진행")

    # 정보 표 (좌측)
    info_top = inner_y + inner_h - 64
    line_h = 18
    info_x_label = inner_x
    info_x_value = inner_x + 28 * mm
    rows = [
        ("상품명", job.product_name),
        ("옵션", job.option_name or "-"),
        ("수량", f"{job.quantity}"),
        ("편집번호", job.wepnp_seqno),
    ]
    for i, (label, value) in enumerate(rows):
        y = info_top - i * line_h
        c.setFont(bold_font, 10)
        c.drawString(info_x_label, y, label)
        c.setFont(regular_font, 11)
        # 긴 텍스트는 자름
        c.drawString(info_x_value, y, value[:80])

    # 미리보기 이미지 (좌측 하단 ~ 중앙)
    preview_top = info_top - len(rows) * line_h - 8
    preview_h = preview_top - inner_y - 64  # 비고 영역 위까지
    if job.preview_image_path and os.path.exists(job.preview_image_path):
        try:
            from reportlab.lib.utils import ImageReader

            img_reader = ImageReader(job.preview_image_path)
            iw, ih = img_reader.getSize()
            max_w = inner_w
            max_h = preview_h
            scale = min(max_w / iw, max_h / ih)
            draw_w = iw * scale
            draw_h = ih * scale
            draw_x = inner_x + (inner_w - draw_w) / 2
            draw_y = preview_top - draw_h
            c.drawImage(img_reader, draw_x, draw_y, width=draw_w, height=draw_h, mask="auto")
        except Exception:
            logger.exception("미리보기 이미지 삽입 실패")

    # 비고 영역 (하단)
    note_y = inner_y + 12
    note_h = 48
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.rect(inner_x, note_y, inner_w, note_h)
    c.setFont(bold_font, 10)
    c.drawString(inner_x + 4, note_y + note_h - 14, "비고")

    c.showPage()
    c.save()
    logger.info("작업지시서 PDF 생성: %s", dest_path)
    return dest_path
