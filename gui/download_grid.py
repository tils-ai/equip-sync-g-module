"""DownloadGrid — 출력 큐 카드 그리드 (대기/실패/완료 탭, 반응형 줄바꿈).

폴더처럼 고정 크기 카드를 컨테이너 폭에 맞춰 줄바꿈 배치하고, 상단 세그먼트로
상태 탭을 전환한다.
  - 대기(ready): [출력] 클릭으로 장비 전송 (전송 중인 항목도 이 탭에서 표시)
  - 실패(failed): [재시도] 클릭으로 재전송, 실패 사유 표시
  - 완료(done): 전송완료 이력 (딤 처리, 버튼 없음)

설계: dps-store/docs/print/20260609-garment-worker-gated-print.md §5-2,
      dps-store/docs/print/20260611-garment-client-gui-design.md
콜백(on_ready/on_printing/on_item_done/on_item_failed/on_item_removed)은
백그라운드 스레드에서 오므로, 호출부(gui/app.py)가 self.after(0, ...) 로
메인 스레드 마샬링 후 이 위젯 메서드를 부른다.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

import customtkinter as ctk

from fonts import family as _font_family

from . import theme

logger = logging.getLogger(__name__)

_THUMB_PX = 158
_CARD_W = 186            # 카드 고정 폭 — 폭 기반 열 수 계산의 단위
_CARD_PAD = 8            # 카드 좌우 패딩(각각)
_CARD_TOTAL = _CARD_W + _CARD_PAD * 2

# 잉크 모드 — 흰옷=Color only(0), 컬러옷=White+Color(2). config.INK 의 의미와 동일.
INK_COLOR = 0
INK_WHITE_COLOR = 2

_FILTERS = ["ready", "failed", "done"]
_FILTER_LABELS = {"ready": "대기", "failed": "실패", "done": "완료"}
_LABEL_TO_FILTER = {v: k for k, v in _FILTER_LABELS.items()}

# 상태 강조 — 테두리색(SOLID) + 배경 tint(SOFT) + 텍스트/아이콘 3중.
_STATUS_BORDER = {
    "ready": theme.BORDER,
    "printing": theme.PROGRESS,
    "failed": theme.DANGER,
    "done": theme.SUCCESS,
}
_STATUS_BG = {
    "ready": theme.SURFACE,
    "printing": theme.PROGRESS_SOFT,
    "failed": theme.DANGER_SOFT,
    "done": theme.SUCCESS_SOFT,
}


def _make_thumb(path: str, size: int):
    """디자인 파일 첫 페이지를 PIL 썸네일로. 실패 시 None (placeholder 표시)."""
    try:
        from PIL import Image

        from processor import _flatten_to_white, _load_images

        images = _load_images(path)
        if not images:
            return None
        # 투명 배경을 흰색으로 평탄화 — 실제 출력(흰 의류) 기준 미리보기
        img = _flatten_to_white(images[0])
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        return img
    except Exception as e:
        logger.debug("썸네일 생성 실패(%s): %s", os.path.basename(path), e)
        return None


class DesignCard(ctk.CTkFrame):
    """디자인 1건 카드 — 썸네일 + 이름 + 배지 + 상태별 버튼."""

    def __init__(self, parent, item, on_print: Callable[[str], None]) -> None:
        super().__init__(
            parent,
            fg_color=theme.SURFACE,
            corner_radius=theme.CORNER_MD,
            width=_CARD_W,
            border_width=2,
            border_color=theme.BORDER,
        )
        self.item_id = item.id
        self.status = getattr(item, "status", "ready") or "ready"
        self._on_print = on_print
        self.grid_columnconfigure(0, weight=1)

        job = item.job or {}
        order_number = job.get("orderNumber", "")
        idx = job.get("itemIndex", 1)
        total = job.get("itemTotal", 1)
        product = job.get("productName", "")
        option = job.get("optionName") or ""
        self._has_work_order = bool(getattr(item, "do_work_order", False))

        # 썸네일 박스 (placeholder → 백그라운드 로드 후 교체)
        self._thumb = ctk.CTkLabel(
            self,
            text="🖼",
            width=_THUMB_PX,
            height=_THUMB_PX,
            fg_color=theme.SURFACE_2,
            corner_radius=theme.CORNER_MD,
            font=ctk.CTkFont(family=_font_family(), size=30),
            text_color=theme.TEXT_MUTED,
        )
        self._thumb.grid(row=0, column=0, padx=theme.SP_2, pady=(theme.SP_2, theme.SP_1), sticky="ew")

        # 주문번호 + 순번
        seq = f"  #{idx}/{total}" if total and total > 1 else ""
        ctk.CTkLabel(
            self,
            text=f"{order_number}{seq}",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY_LG, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=1, column=0, padx=theme.SP_2, sticky="ew")

        # 상품명 / 옵션
        sub = product + (f" · {option}" if option else "")
        ctk.CTkLabel(
            self,
            text=sub,
            anchor="w",
            wraplength=_THUMB_PX,
            justify="left",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            text_color=theme.TEXT_SUB,
        ).grid(row=2, column=0, padx=theme.SP_2, sticky="ew")

        # 배지 — 지시서 포함 / 아동 플레이트 / 수량
        badges = []
        if self._has_work_order:
            badges.append("📄 지시서")
        if job.get("needsPlateChange"):
            badges.append("👶 아동")
        qty = int(job.get("quantity", 1) or 1)
        if qty > 1:
            badges.append(f"×{qty}")
        ctk.CTkLabel(
            self,
            text="   ".join(badges) if badges else " ",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            text_color=theme.ACCENT,
        ).grid(row=3, column=0, padx=theme.SP_2, pady=(theme.SP_1, 0), sticky="ew")

        # 액션 버튼 2개 — 흰옷(Color) / 컬러옷(White+Color). 옷 색에 따라 즉석 선택.
        self._btns = ctk.CTkFrame(self, fg_color="transparent")
        self._btns.grid(row=4, column=0, padx=theme.SP_2, pady=theme.SP_1, sticky="ew")
        self._btns.grid_columnconfigure((0, 1), weight=1, uniform="ink")

        _bfont = ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY, weight="bold")
        self._btn_white = ctk.CTkButton(
            self._btns,
            text="흰옷 출력",
            height=theme.TOUCH_LG,
            corner_radius=theme.CORNER_SM,
            command=lambda: self._click(INK_COLOR),
            font=_bfont,
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            text_color=theme.TEXT_ON_ACCENT,
        )
        self._btn_white.grid(row=0, column=0, padx=(0, theme.SP_1), sticky="ew")
        self._btn_color = ctk.CTkButton(
            self._btns,
            text="컬러옷 출력",
            height=theme.TOUCH_LG,
            corner_radius=theme.CORNER_SM,
            command=lambda: self._click(INK_WHITE_COLOR),
            font=_bfont,
            fg_color=theme.ACCENT_ALT,
            hover_color=theme.ACCENT_ALT_HOVER,
            text_color=theme.TEXT_ON_ACCENT,
        )
        self._btn_color.grid(row=0, column=1, padx=(theme.SP_1, 0), sticky="ew")

        # 상태 라벨 (전송 중/실패 사유/완료)
        self._status_lbl = ctk.CTkLabel(
            self,
            text="",
            anchor="center",
            wraplength=_THUMB_PX,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            text_color=theme.TEXT_MUTED,
        )
        self._status_lbl.grid(row=5, column=0, padx=theme.SP_2, pady=(0, theme.SP_2), sticky="ew")

        self._apply_status(self.status, getattr(item, "error_reason", "") or "")
        self._load_thumb_async(item.download_path)

    # ── 그룹(탭) ──
    def group(self) -> str:
        """필터 탭 그룹 — 전송 중(printing)은 대기 탭에서 표시."""
        return "ready" if self.status in ("ready", "printing") else self.status

    # ── 썸네일 ──
    def _load_thumb_async(self, path: str) -> None:
        def worker():
            img = _make_thumb(path, _THUMB_PX)
            if img is None:
                return
            try:
                self.after(0, lambda: self._set_thumb(img))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _set_thumb(self, pil_img) -> None:
        try:
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
            self._thumb.configure(image=ctk_img, text="")
            self._thumb.image = ctk_img  # 참조 유지 (GC 방지)
        except Exception:
            logger.debug("썸네일 표시 실패", exc_info=True)

    def _click(self, ink: int) -> None:
        self._on_print(self.item_id, ink)

    def _set_buttons(self, state: str) -> None:
        self._btn_white.configure(state=state)
        self._btn_color.configure(state=state)

    # ── 상태 전환 ──
    def _apply_status(self, status: str, reason: str = "") -> None:
        self.status = status
        self.configure(
            border_color=_STATUS_BORDER.get(status, theme.BORDER),
            fg_color=_STATUS_BG.get(status, theme.SURFACE),
        )
        if status == "ready":
            self._btns.grid()
            self._set_buttons("normal")
            self._status_lbl.grid_remove()  # 사유 없음 — 빈 칸 차지 방지
        elif status == "printing":
            self._btns.grid()
            self._set_buttons("disabled")
            self._status_lbl.grid()
            self._status_lbl.configure(text=reason or "⟳ 장비로 전송 중", text_color=theme.PROGRESS)
        elif status == "failed":
            # 실패 시 두 버튼을 다시 살려 잉크를 골라 재시도.
            self._btns.grid()
            self._set_buttons("normal")
            self._status_lbl.grid()
            self._status_lbl.configure(text=f"실패 — {reason} · 잉크 선택 후 재시도" if reason else "전송 실패 · 재시도",
                                       text_color=theme.DANGER)
        elif status == "done":
            self._btns.grid_remove()
            self._status_lbl.grid()
            self._status_lbl.configure(text="✅ 전송완료", text_color=theme.SUCCESS)

    def set_printing(self, printer: str) -> None:
        suffix = f" · {printer}" if printer else ""
        self._apply_status("printing", f"전송 중{suffix}")

    def set_failed(self, reason: str = "") -> None:
        self._apply_status("failed", reason)

    def set_done(self) -> None:
        self._apply_status("done")


class DownloadGrid(ctk.CTkFrame):
    """상태 탭 + 반응형 카드 그리드 컨테이너."""

    def __init__(self, parent, on_print: Callable[[str], None]) -> None:
        super().__init__(parent, fg_color="transparent")
        self._on_print = on_print
        self._cards: dict[str, DesignCard] = {}
        self._order: list[str] = []
        self._filter = "ready"
        self._cols = 1

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── 탭(세그먼트) + 카운트 요약 ──
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        bar.grid_columnconfigure(1, weight=1)

        self._seg = ctk.CTkSegmentedButton(
            bar,
            values=[_FILTER_LABELS[f] for f in _FILTERS],
            command=self._on_tab_changed,
            height=36,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY, weight="bold"),
            selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER,
        )
        self._seg.set(_FILTER_LABELS["ready"])
        self._seg.grid(row=0, column=0, sticky="w")

        self._summary = ctk.CTkLabel(
            bar,
            text="",
            anchor="e",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            text_color=theme.TEXT_MUTED,
        )
        self._summary.grid(row=0, column=1, sticky="e", padx=(theme.SP_2, theme.SP_1))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=2, column=0, sticky="nsew", padx=4, pady=(4, 4))
        self._scroll.bind("<Configure>", self._on_resize)

        self._empty = ctk.CTkLabel(
            self._scroll,
            text="",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY),
            text_color=theme.TEXT_MUTED,
        )
        self._reflow()

    # ── 공개 API (메인 스레드에서 호출) ──
    def add_item(self, item) -> None:
        item_id = getattr(item, "id", "")
        if not item_id or item_id in self._cards:
            return
        card = DesignCard(self._scroll, item, self._on_print)
        self._cards[item_id] = card
        self._order.append(item_id)
        self._reflow()

    def remove_item(self, item_id: str) -> None:
        card = self._cards.pop(item_id, None)
        if card is not None:
            card.destroy()
        if item_id in self._order:
            self._order.remove(item_id)
        self._reflow()

    def set_printing(self, item_id: str, printer: str) -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.set_printing(printer)
            self._reflow()

    def set_failed(self, item_id: str, reason: str = "") -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.set_failed(reason)
            self._reflow()

    def set_done(self, item_id: str) -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.set_done()
            self._reflow()

    def clear(self) -> None:
        for card in self._cards.values():
            card.destroy()
        self._cards.clear()
        self._order.clear()
        self._reflow()

    # ── 내부 ──
    def _on_tab_changed(self, label: str) -> None:
        self._filter = _LABEL_TO_FILTER.get(label, "ready")
        self._reflow()

    def _on_resize(self, event) -> None:
        cols = max(1, int(event.width // _CARD_TOTAL))
        if cols != self._cols:
            self._cols = cols
            self._reflow()

    def _counts(self) -> dict[str, int]:
        c = {"ready": 0, "failed": 0, "done": 0}
        for card in self._cards.values():
            c[card.group()] = c.get(card.group(), 0) + 1
        return c

    def _reflow(self) -> None:
        counts = self._counts()
        visible = [iid for iid in self._order if self._cards[iid].group() == self._filter]
        visible_set = set(visible)

        # 비표시 카드는 숨김
        for iid, card in self._cards.items():
            if iid not in visible_set:
                card.grid_remove()

        cols = max(1, self._cols)
        for idx, iid in enumerate(visible):
            self._cards[iid].grid(
                row=idx // cols + 1,  # row 0 은 empty 라벨 자리
                column=idx % cols,
                padx=_CARD_PAD,
                pady=_CARD_PAD,
                sticky="n",
            )

        # 카운트 요약 + 빈 상태
        self._summary.configure(
            text=f"대기 {counts['ready']} · 실패 {counts['failed']} · 완료 {counts['done']}"
        )
        if not visible:
            self._empty.configure(text=self._empty_text())
            self._empty.grid(row=0, column=0, columnspan=max(1, cols), padx=12, pady=24, sticky="w")
        else:
            self._empty.grid_remove()

    def _empty_text(self) -> str:
        return {
            "ready": "출력 대기 중인 디자인이 없습니다.",
            "failed": "실패한 항목이 없습니다.",
            "done": "전송완료 이력이 없습니다.",
        }.get(self._filter, "")
