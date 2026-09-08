"""작업지시서 PDF 생성 — reportlab 기반.

dps-store/entities/print/pdf/work-order-pdf.ts(브라우저 다운로드용)와 같은 A4 1장 양식을
가먼트 클라이언트(Python) 측에서 재현한다. 두 곳에서 나온 지시서가 달라 보이면 작업자가
양식을 두 가지 익혀야 한다.

레이아웃은 웹(96 DPI px)을 기준으로 잡고 `px()` 로 pt 환산한다.

위에서 아래로:
- 상단 밴드 — 세트면 「세트 주문 + SET 1 / 3」, 한 장짜리면 「단일 주문」. 우측에 주문번호·주문일시
- 굵은 구분선 → 제목 「작업지시서」 + 부제
- 정보 표 — 상품명·편집번호 / 옵션·수량을 두 쌍씩 한 줄에, 디자인 파일·출력 장비·비고는 전체 폭
- 이미지 영역 — 좌 완성 예시(에디터 썸네일) / 우 생산 이미지(실제 도안). 남는 세로를 전부 쓴다
- 하단 바 — 작업 상세 QR + 안내, 세트면 세트 정보 재표기
- 워터마크는 위아래만 (좌우 세로 워터마크는 본문 폭을 갉아먹어 뺐다)
"""

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
    #: 생산 이미지 — 실제로 프린터에 넘긴 도안 파일(이미지일 때만)
    preview_image_path: Optional[str] = None
    #: 썸네일 — 에디터 미리보기(인쇄 면 수만큼). 작업자가 완성 형태를 대조하는 용도
    thumbnail_paths: list[str] = field(default_factory=list)
    design_filename: Optional[str] = None
    printer_name: Optional[str] = None
    #: 주문일시 — 상단 밴드에 표기. 서버가 안 내려주면(구버전) 그 줄만 빠진다
    ordered_at: Optional[str] = None
    #: 출력 플레이트 교체 대상 — 경고 배너 + 옵션 칸 강조
    needs_plate_change: bool = False


#: 웹(96 DPI px) 치수를 pt 로 옮기는 배율. 두 양식을 같은 숫자로 맞추기 위한 것
PT_PER_PX = 0.75


def px(value: float) -> float:
    """웹 px 치수를 PDF pt 로."""
    return value * PT_PER_PX


def format_ordered_at(raw: Optional[str]) -> Optional[str]:
    """서버가 내려준 ISO 주문일시를 `2026. 08. 03. 14:52` 로.

    구버전 서버는 이 값을 안 내려준다. 그때는 밴드에서 주문일시 줄만 빠진다.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("주문일시 파싱 실패 — 표기 생략: %s", raw)
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()  # 매장 PC 로컬시각(KST)으로 옮겨 적는다
    return dt.strftime("%Y. %m. %d. %H:%M")


def set_info(item_index: int, item_total: int) -> dict:
    """세트 주문 여부와 순번.

    예전에는 주문번호 뒤에 `-01(3)` 을 붙여 세트를 구분했다. 작업자가 그 괄호 숫자를
    주문번호의 일부로 읽어 「몇 장 중 몇 번째인지」가 눈에 들어오지 않았다.
    주문번호와 세트 순번을 아예 다른 자리에 둔다.
    """
    total = item_total if item_total and item_total > 0 else 1
    return {
        # 지시서가 2장 이상 나오는 주문만 세트다 (한 장짜리 주문에는 SET 영역을 넣지 않는다)
        "is_set": total > 1,
        "index": item_index,
        "total": total,
        "label": f"SET {item_index} / {total}",
        "description": f"총 {total}개 중 {item_index}번째 작업",
    }


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


def _system_font_path(name: str) -> Optional[str]:
    """Windows 시스템 폰트(C:\\Windows\\Fonts) 경로. 없으면 None."""
    if os.name != "nt":
        return None
    windir = os.environ.get("WINDIR", r"C:\Windows")
    p = Path(windir) / "Fonts" / name
    return str(p) if p.exists() else None


def _register_fonts() -> tuple[str, str]:
    """한글 폰트 등록. 반환: (regular_name, bold_name).

    임베딩 가능한 TTF 를 최우선으로 쓴다. 비임베딩 CID 폰트로 떨어지면 PDF 안에 폰트가 실리지
    않아, 출력 PC 의 poppler(pdftocairo) 가 대체 폰트를 못 찾을 때 **글자만 통째로 빠진**
    인쇄물이 나온다(괘선·이미지는 정상). 그래서 CID 는 최후 수단이며 경고를 남긴다.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    # 1) 번들 Pretendard (TTF — reportlab 은 CFF 기반 .otf 를 읽지 못한다)
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

    # 2) Windows 기본 한글 폰트 (맑은 고딕) — 역시 임베딩된다
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

    # 3) 비임베딩 CID — 출력 PC 환경에 따라 글자가 인쇄되지 않을 수 있다
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


def _fit(c, text: str, font: str, size: float, max_w: float) -> str:
    """칸 폭을 넘으면 말줄임. 실제 글자 폭으로 잰다(문자 수 어림짐작은 한글에서 크게 틀린다)."""
    if not text:
        return ""
    if c.stringWidth(text, font, size) <= max_w:
        return text
    ell = "…"
    cut = text
    while cut and c.stringWidth(cut + ell, font, size) > max_w:
        cut = cut[:-1]
    return (cut + ell) if cut else ell


def _draw_watermark(c, page_w, page_h, pad_x, regular_font, bold_font, left, mid, right):
    """위아래 워터마크.

    좌우 세로 워터마크는 뺐다(웹과 동일). 양쪽에서 본문 폭을 갉아먹어 표와 이미지가 눌렸고,
    위아래만으로도 분실 시 출처 추적에는 충분하다.
    """
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
    """상단 밴드 — 세트면 SET 순번을, 한 장짜리 주문이면 그 사실을 명시한다.

    현장 프린터가 흑백인 지점이 있어 색이 아니라 **명도**(검정 바탕 + 흰 글씨)로 구분한다.
    웹은 아이콘에 이모지를 쓰지만 PDF 임베딩 폰트에는 컬러 이모지가 없어 「■」로 대신한다.

    반환: 밴드 아래 y 좌표.
    """
    from reportlab.lib.colors import HexColor

    band_h = px(88)
    y = top - band_h
    left_w = px(205)
    right_w = px(215) if info["is_set"] else 0

    # 바깥 테두리
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(px(2))
    c.rect(x, y, w, band_h, stroke=1, fill=0)

    # 좌측 검정 블록
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
        # 가운데 — SET 순번
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

        # 우측 — 주문번호 / 주문일시
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
        # 한 장짜리 주문 — 주문번호를 크게, 주문일시는 오른쪽 끝
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
    """정보 표.

    짧은 값은 두 쌍씩 한 줄에 담는다(`pairs`). 한 줄에 한 항목씩 쌓으면 표만 지면 절반을
    먹어 정작 확인해야 할 이미지가 눌린다. 긴 값(디자인 파일 등)은 전체 폭을 쓴다(`full_rows`).

    반환: 표 아래 y 좌표.
    """
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
    """이미지 영역 — 완성 예시(좌)와 생산 이미지(우)를 갈라 각각 라벨을 붙인다.

    한 줄에 섞어 늘어놓으면 작업자가 완성 예시를 출력 파일로 착각한다. 남는 세로를 전부
    쓰므로 지면이 남거나 모자라지 않는다.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader

    height = top - bottom
    if height <= px(60) or not panes:
        return

    c.setStrokeColor(HexColor("#dddddd"))
    c.setLineWidth(px(1))
    c.rect(x, bottom, w, height, stroke=1, fill=0)

    pane_w = w / len(panes)
    # 각주가 한쪽에만 있어도 배지 높이는 칸끼리 맞춘다 — 어긋나면 두 칸이 다른 표처럼 보인다
    note_h = px(16) if any(note for _, _, note in panes) else 0
    for i, (caption, paths, note) in enumerate(panes):
        pane_x = x + pane_w * i
        if i > 0:
            c.line(pane_x, bottom, pane_x, bottom + height)

        pill_h = px(24)
        pad = px(12)
        img_h = height - pad * 2 - pill_h - px(8) - note_h
        img_w = pane_w - pad * 2

        # 이미지 (여러 장이면 가로로 나눠 담는다)
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

        # 캡션 — 검정 배지
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
    """하단 — 작업 상세 QR 과 세트 정보.

    작업 중 상단이 가려지거나 지시서를 여러 장 펼쳐 둔 상황에서도 같은 주문인지 확인할 수
    있도록 세트 정보를 한 번 더 적는다.
    """
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
    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold_font, px(14))
    c.drawString(text_x, bottom + bar_h / 2 + px(14), "작업 상세 QR")
    c.setFillColor(HexColor("#555555"))
    c.setFont(regular_font, px(11))
    c.drawString(text_x, bottom + bar_h / 2 - px(4), "QR 코드를 스캔하면")
    c.drawString(text_x, bottom + bar_h / 2 - px(20), "상세 주문 정보를 확인할 수 있습니다.")

    if not info["is_set"]:
        return

    div_x = text_x + px(150)
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
    """A4 1장 작업지시서 PDF — 웹 다운로드와 동일 레이아웃."""
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

    # 상단 밴드 → 굵은 구분선
    y = _draw_band(c, job, info, inner_x, page_h - pad_y, inner_w, regular_font, bold_font)
    y -= px(12)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(px(3))
    c.line(inner_x, y, inner_x + inner_w, y)

    # 제목 + 부제
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

    # 출력 플레이트 교체 대상 경고 배너
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

    # 정보 표
    pairs = [
        ("상품명", job.product_name, "편집번호", job.wepnp_seqno, False),
        ("옵션", job.option_name or "-", "수량", f"{job.quantity}개", job.needs_plate_change),
    ]
    full_rows = [("디자인 파일", job.design_filename or "-", True, False)]
    if job.printer_name:
        full_rows.append(("출력 장비", job.printer_name, False, False))
    full_rows.append(("비고", "-", False, True))
    y = _draw_table(c, inner_x, y, inner_w, regular_font, bold_font, pairs, full_rows)

    # 하단 바 → 그 위 남는 자리를 이미지가 전부 쓴다
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
