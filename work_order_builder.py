
from __future__ import annotations

import logging
import os
from datetime import datetime
from dataclasses import dataclass, field
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
    thumbnail_paths: list[str] = field(default_factory=list)
    design_filename: Optional[str] = None
    printer_name: Optional[str] = None
    ordered_at: Optional[str] = None
    needs_plate_change: bool = False


PT_PER_PX = 0.75


def px(value: float) -> float:
    return value * PT_PER_PX


def format_ordered_at(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("주문일시 파싱 실패 — 표기 생략: %s", raw)
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%Y. %m. %d. %H:%M")


def set_info(item_index: int, item_total: int) -> dict:
    total = item_total if item_total and item_total > 0 else 1
    return {
        "is_set": total > 1,
        "index": item_index,
        "total": total,
        "label": f"SET {item_index} / {total}",
        "description": f"총 {total}개 중 {item_index}번째 작업",
    }


def _font_path(name: str) -> Optional[str]:
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


def _system_font_path(name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    windir = os.environ.get("WINDIR", r"C:\Windows")
    p = Path(windir) / "Fonts" / name
    return str(p) if p.exists() else None


def _register_fonts() -> tuple[str, str]:
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
            logger.exception("Pretendard ttf 등록 실패 — 시스템 폰트 폴백")
    else:
        logger.warning("번들 Pretendard ttf 없음 (assets/fonts) — 시스템 폰트 폴백")

    sys_regular = _system_font_path("malgun.ttf")
    sys_bold = _system_font_path("malgunbd.ttf") or sys_regular
    if sys_regular and sys_bold:
        try:
            pdfmetrics.registerFont(TTFont("MalgunGothic", sys_regular))
            pdfmetrics.registerFont(TTFont("MalgunGothic-Bold", sys_bold))
            logger.warning("맑은 고딕으로 작업지시서를 생성한다 (번들 Pretendard 사용 불가)")
            return "MalgunGothic", "MalgunGothic-Bold"
        except Exception:
            logger.exception("맑은 고딕 등록 실패 — CID 폴백")

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
        logger.error(
            "임베딩 폰트를 찾지 못해 CID 폰트로 생성한다 — 인쇄 시 글자가 비어 나올 수 있음"
        )
        return "HYSMyeongJo-Medium", "HYGothic-Medium"
    except Exception:
        logger.exception("CIDFont 등록 실패 — Helvetica 폴백 (한글 미지원)")
        return "Helvetica", "Helvetica-Bold"


def _make_qr(url: str):
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


def _fit(c, text: str, font: str, size: float, max_w: float) -> str:
    if not text:
        return ""
    if c.stringWidth(text, font, size) <= max_w:
        return text
    ell = "…"
    cut = text
    while cut and c.stringWidth(cut + ell, font, size) > max_w:
        cut = cut[:-1]
    return (cut + ell) if cut else ell


def _wrap(c, text: str, font: str, size: float, max_w: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if current and c.stringWidth(candidate, font, size) > max_w:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_watermark(c, page_w, page_h, pad_x, regular_font, bold_font, left, mid, right):
    from reportlab.lib.colors import HexColor

    wm_size = px(10)
    c.saveState()
    c.setFillColor(HexColor("#dc2626"))
    for y in (page_h - px(10) - wm_size, px(10)):
        c.setFont(regular_font, wm_size)
        c.drawString(pad_x, y, left)
        c.setFont(bold_font, wm_size)
        c.drawCentredString(page_w / 2, y, mid)
        c.setFont(regular_font, wm_size)
        c.drawRightString(page_w - pad_x, y, right)
    c.restoreState()


def _draw_band(c, job, info, x, top, w, regular_font, bold_font) -> float:
    from reportlab.lib.colors import HexColor

    band_h = px(88)
    y = top - band_h
    left_w = px(205)
    right_w = px(215) if info["is_set"] else 0

    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(px(2))
    c.rect(x, y, w, band_h, stroke=1, fill=0)

    c.setFillColorRGB(0, 0, 0)
    c.rect(x, y, left_w, band_h, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(bold_font, px(22))
    c.drawString(x + px(14), y + band_h - px(14) - px(22) * 0.8, "■ 세트 주문" if info["is_set"] else "■ 단일 주문")
    c.setFont(regular_font, px(11))
    sub_lines = (
        ["동일 주문의 여러 디자인 중", "현재 작업지시서입니다."]
        if info["is_set"]
        else ["이 주문의 작업지시서는", "이 1장이 전부입니다."]
    )
    line_y = y + band_h - px(46)
    for line in sub_lines:
        c.drawString(x + px(14), line_y, line)
        line_y -= px(15)

    if info["is_set"]:
        mid_x = x + left_w
        mid_w = w - left_w - right_w
        c.setFillColor(HexColor("#f5f5f5"))
        c.rect(mid_x, y, mid_w, band_h, stroke=0, fill=1)
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(px(2))
        c.line(mid_x + mid_w, y, mid_x + mid_w, y + band_h)
        c.setFillColorRGB(0, 0, 0)
        c.setFont(bold_font, px(34))
        c.drawCentredString(mid_x + mid_w / 2, y + band_h / 2 - px(2), info["label"])
        c.setFont(regular_font, px(13))
        c.drawCentredString(mid_x + mid_w / 2, y + band_h / 2 - px(22), f"({info['description']})")

        right_x = x + w - right_w
        c.setFillColor(HexColor("#444444"))
        c.setFont(regular_font, px(11))
        c.drawString(right_x + px(14), y + band_h - px(26), "주문번호")
        c.setFillColorRGB(0, 0, 0)
        c.setFont(bold_font, px(19))
        c.drawString(
            right_x + px(14),
            y + band_h - px(48),
            _fit(c, job.order_number, bold_font, px(19), right_w - px(28)),
        )
        if job.ordered_at:
            c.setStrokeColor(HexColor("#dddddd"))
            c.setLineWidth(px(1))
            c.line(right_x + px(14), y + px(24), x + w - px(14), y + px(24))
            c.setFillColor(HexColor("#555555"))
            c.setFont(regular_font, px(11))
            c.drawString(right_x + px(14), y + px(12), f"주문일시 : {job.ordered_at}")
    else:
        c.setFillColor(HexColor("#444444"))
        c.setFont(regular_font, px(11))
        c.drawString(x + left_w + px(18), y + band_h / 2 + px(6), "주문번호")
        c.setFillColorRGB(0, 0, 0)
        c.setFont(bold_font, px(26))
        c.drawString(x + left_w + px(18), y + band_h / 2 - px(20), job.order_number)
        if job.ordered_at:
            c.setFillColor(HexColor("#555555"))
            c.setFont(regular_font, px(11))
            c.drawRightString(x + w - px(18), y + band_h / 2 + px(6), "주문일시")
            c.setFillColorRGB(0, 0, 0)
            c.setFont(regular_font, px(14))
            c.drawRightString(x + w - px(18), y + band_h / 2 - px(12), job.ordered_at)

    return y


def _draw_table(c, x, top, w, regular_font, bold_font, pairs, full_rows) -> float:
    from reportlab.lib.colors import HexColor

    font_size = px(15)
    pad_x = px(14)
    pad_y = px(9)
    row_h = font_size + pad_y * 2
    label_w = px(110)
    value_w = (w - label_w * 2) / 2

    border = HexColor("#dddddd")
    label_bg = HexColor("#f5f5f5")

    def cell(cx, cy, cw, text, is_label, font, size, color=None, bg=None):
        if bg is not None:
            c.setFillColor(bg)
            c.rect(cx, cy, cw, row_h, stroke=0, fill=1)
        c.setStrokeColor(border)
        c.setLineWidth(px(1))
        c.rect(cx, cy, cw, row_h, stroke=1, fill=0)
        c.setFillColor(color or HexColor("#000000"))
        c.setFont(font, size)
        c.drawString(cx + pad_x, cy + (row_h - size) / 2 + size * 0.25, _fit(c, text, font, size, cw - pad_x * 2))

    y = top
    for left_label, left_value, right_label, right_value, highlight in pairs:
        y -= row_h
        cell(x, y, label_w, left_label, True, bold_font, font_size, bg=label_bg)
        cell(
            x + label_w,
            y,
            value_w,
            left_value,
            False,
            bold_font if highlight else regular_font,
            font_size,
            color=HexColor("#b45309") if highlight else None,
            bg=HexColor("#fff7ed") if highlight else None,
        )
        cell(x + label_w + value_w, y, label_w, right_label, True, bold_font, font_size, bg=label_bg)
        cell(x + label_w * 2 + value_w, y, value_w, right_value, False, regular_font, font_size)

    for label, value, mono, muted in full_rows:
        y -= row_h
        cell(x, y, label_w, label, True, bold_font, font_size, bg=label_bg)
        size = px(13) if mono else font_size
        cell(
            x + label_w,
            y,
            w - label_w,
            value,
            False,
            regular_font,
            size,
            color=HexColor("#888888") if muted else None,
        )
    return y


def _draw_image_area(c, panes, x, top, w, bottom, regular_font) -> None:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader

    height = top - bottom
    if height <= px(60) or not panes:
        return

    c.setStrokeColor(HexColor("#dddddd"))
    c.setLineWidth(px(1))
    c.rect(x, bottom, w, height, stroke=1, fill=0)

    pane_w = w / len(panes)
    note_h = px(16) if any(note for _, _, note in panes) else 0
    for i, (caption, paths, note) in enumerate(panes):
        pane_x = x + pane_w * i
        if i > 0:
            c.line(pane_x, bottom, pane_x, bottom + height)

        pill_h = px(24)
        pad = px(12)
        img_h = height - pad * 2 - pill_h - px(8) - note_h
        img_w = pane_w - pad * 2

        if paths and img_h > 0:
            slot_w = (img_w - px(8) * (len(paths) - 1)) / len(paths)
            slot_x = pane_x + pad
            for path in paths:
                try:
                    reader = ImageReader(path)
                    iw, ih = reader.getSize()
                    scale = min(slot_w / iw, img_h / ih)
                    dw, dh = iw * scale, ih * scale
                    c.drawImage(
                        reader,
                        slot_x + (slot_w - dw) / 2,
                        bottom + height - pad - img_h + (img_h - dh) / 2,
                        width=dw,
                        height=dh,
                        mask="auto",
                    )
                except Exception:
                    logger.exception("작업지시서 이미지 삽입 실패: %s", path)
                slot_x += slot_w + px(8)

        pill_y = bottom + pad + note_h
        c.setFont(regular_font, px(13))
        text_w = c.stringWidth(caption, regular_font, px(13))
        pill_w = text_w + px(32)
        pill_x = pane_x + (pane_w - pill_w) / 2
        c.setFillColorRGB(0, 0, 0)
        c.roundRect(pill_x, pill_y, pill_w, pill_h, px(8), stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(pane_x + pane_w / 2, pill_y + pill_h / 2 - px(4), caption)

        if note:
            c.setFillColor(HexColor("#666666"))
            c.setFont(regular_font, px(10))
            c.drawCentredString(pane_x + pane_w / 2, bottom + pad, note)


def _draw_bottom_bar(c, job, info, x, bottom, w, regular_font, bold_font) -> None:
    import io as _io

    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader

    bar_h = px(110)
    c.setStrokeColor(HexColor("#bbbbbb"))
    c.setLineWidth(px(1))
    c.rect(x, bottom, w, bar_h, stroke=1, fill=0)

    qr_size = px(84)
    qr_x = x + px(14)
    qr_y = bottom + (bar_h - qr_size) / 2
    try:
        buf = _io.BytesIO()
        _make_qr(job.work_url).save(buf, format="PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception:
        logger.exception("QR 생성 실패 — QR 생략하고 진행")

    text_x = qr_x + qr_size + px(10)
    div_x = text_x + px(150)
    text_w = (div_x - text_x - px(12)) if info["is_set"] else px(240)

    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold_font, px(14))
    c.drawString(text_x, bottom + bar_h / 2 + px(14), "작업 상세 QR")

    c.setFillColor(HexColor("#555555"))
    guide_size = px(10) if info["is_set"] else px(11)
    c.setFont(regular_font, guide_size)
    lines = _wrap(c, "QR 코드를 스캔하면 상세 주문 정보를 확인할 수 있습니다.", regular_font, guide_size, text_w)
    line_y = bottom + bar_h / 2 - px(4)
    for line in lines[:3]:
        c.drawString(text_x, line_y, line)
        line_y -= guide_size + px(4)

    if not info["is_set"]:
        return

    c.setStrokeColor(HexColor("#cccccc"))
    c.line(div_x, bottom + px(10), div_x, bottom + bar_h - px(10))

    info_x = div_x + px(16)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold_font, px(13))
    c.drawString(info_x, bottom + bar_h - px(24), "세트 주문 정보")

    box_w, box_h = px(150), px(52)
    box_y = bottom + px(16)
    c.setFillColor(HexColor("#f1f1f1"))
    c.roundRect(info_x, box_y, box_w, box_h, px(6), stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold_font, px(22))
    c.drawCentredString(info_x + box_w / 2, box_y + box_h - px(26), info["label"])
    c.setFont(regular_font, px(11))
    c.drawCentredString(info_x + box_w / 2, box_y + px(8), f"({info['description']})")

    note_x = info_x + box_w + px(14)
    c.setFillColor(HexColor("#333333"))
    c.setFont(regular_font, px(11))
    c.drawString(note_x, box_y + box_h - px(14), f"※ 이 작업지시서는 동일 주문({job.order_number})의")
    c.drawString(note_x, box_y + box_h - px(30), f"{info['total']}개 작업 중 {info['index']}번째 작업입니다.")


def build_work_order_pdf(job: WorkOrderJob, dest_path: str) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas

    regular_font, bold_font = _register_fonts()

    page_w, page_h = A4
    c = canvas.Canvas(dest_path, pagesize=A4)
    c.setTitle(f"작업지시서_{job.order_number}_{job.wepnp_seqno}")

    pad_x = px(40)
    pad_y = px(30)
    inner_x = pad_x
    inner_w = page_w - pad_x * 2

    info = set_info(job.item_index, job.item_total)

    _draw_watermark(
        c,
        page_w,
        page_h,
        pad_x,
        regular_font,
        bold_font,
        left=f"{job.brand_name} | {job.tenant_name} | {job.printed_by}",
        mid="⚠ 작업 후 파기 ⚠",
        right=job.work_url,
    )

    y = _draw_band(c, job, info, inner_x, page_h - pad_y, inner_w, regular_font, bold_font)
    y -= px(12)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(px(3))
    c.line(inner_x, y, inner_x + inner_w, y)

    title_size = px(30)
    y -= px(14) + title_size
    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold_font, title_size)
    c.drawCentredString(page_w / 2, y, "작업지시서")
    y -= px(18)
    c.setFillColor(HexColor("#555555"))
    c.setFont(regular_font, px(13))
    c.drawCentredString(page_w / 2, y, "아래와 같이 상품을 제작해 주세요.")
    y -= px(14)

    if job.needs_plate_change:
        banner_h = px(40)
        y -= banner_h
        c.setFillColor(HexColor("#fde68a"))
        c.setStrokeColor(HexColor("#d97706"))
        c.setLineWidth(px(2))
        c.roundRect(inner_x, y, inner_w, banner_h, px(8), stroke=1, fill=1)
        c.setFillColor(HexColor("#92400e"))
        c.setFont(bold_font, px(18))
        c.drawCentredString(page_w / 2, y + banner_h / 2 - px(6), "⚠ 출력 플레이트 교체 대상 ⚠")
        y -= px(12)

    pairs = [
        ("상품명", job.product_name, "편집번호", job.wepnp_seqno, False),
        ("옵션", job.option_name or "-", "수량", f"{job.quantity}개", job.needs_plate_change),
    ]
    full_rows = [("디자인 파일", job.design_filename or "-", True, False)]
    if job.printer_name:
        full_rows.append(("출력 장비", job.printer_name, False, False))
    full_rows.append(("비고", "-", False, True))
    y = _draw_table(c, inner_x, y, inner_w, regular_font, bold_font, pairs, full_rows)

    bar_h = px(110)
    _draw_bottom_bar(c, job, info, inner_x, pad_y, inner_w, regular_font, bold_font)

    panes: list[tuple[str, list[str], str]] = []
    thumbs = [p for p in (job.thumbnail_paths or []) if p and os.path.exists(p)]
    if thumbs:
        panes.append(("완성 예시 이미지", thumbs, "* 실제 출력 색상과 약간의 차이가 있을 수 있습니다."))
    if job.preview_image_path and os.path.exists(job.preview_image_path):
        panes.append(("생산 이미지", [job.preview_image_path], ""))
    _draw_image_area(c, panes, inner_x, y, inner_w, pad_y + bar_h + px(10), regular_font)

    c.showPage()
    c.save()
    logger.info("작업지시서 PDF 생성: %s", dest_path)
    return dest_path
