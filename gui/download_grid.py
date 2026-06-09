"""DownloadGrid — 다운로드 완료(READY) 디자인 썸네일 그리드 (작업자 수동 전송).

폴더처럼 대기 중인 디자인을 카드 그리드로 보여주고, [출력] 클릭으로 장비에 전송한다.
지시서 포함 마크 / 아동 플레이트 경고 배지 표시. 전송 중/실패 상태 표시.

설계: dps-store/docs/print/20260609-garment-worker-gated-print.md §5-2
콜백(on_ready/on_printing/on_item_removed/on_item_failed)은 백그라운드 스레드에서 오므로,
호출부(gui/app.py)에서 self.after(0, ...) 로 메인 스레드 마샬링 후 이 위젯 메서드를 부른다.
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

_THUMB_PX = 150
_COLS = 4


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
    """디자인 1건 카드 — 썸네일 + 이름 + 배지 + [출력] 버튼."""

    def __init__(self, parent, item, on_print: Callable[[str], None]) -> None:
        super().__init__(parent, fg_color=theme.SURFACE, corner_radius=theme.CORNER)
        self.item_id = item.id
        self._on_print = on_print
        self.grid_columnconfigure(0, weight=1)

        job = item.job or {}
        order_number = job.get("orderNumber", "")
        idx = job.get("itemIndex", 1)
        total = job.get("itemTotal", 1)
        product = job.get("productName", "")
        option = job.get("optionName") or ""

        # 썸네일 박스 (placeholder → 백그라운드 로드 후 교체)
        self._thumb = ctk.CTkLabel(
            self,
            text="🖼",
            width=_THUMB_PX,
            height=_THUMB_PX,
            fg_color=theme.SURFACE_2,
            corner_radius=theme.CORNER,
            font=ctk.CTkFont(family=_font_family(), size=28),
            text_color=theme.TEXT_MUTED,
        )
        self._thumb.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")

        # 주문번호 + 순번
        seq = f"  #{idx}/{total}" if total and total > 1 else ""
        ctk.CTkLabel(
            self,
            text=f"{order_number}{seq}",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=12, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=1, column=0, padx=8, sticky="ew")

        # 상품명 / 옵션 (한 줄, 말줄임은 width 로)
        sub = product + (f" · {option}" if option else "")
        ctk.CTkLabel(
            self,
            text=sub,
            anchor="w",
            wraplength=_THUMB_PX,
            justify="left",
            font=ctk.CTkFont(family=_font_family(), size=11),
            text_color=theme.TEXT_MUTED,
        ).grid(row=2, column=0, padx=8, sticky="ew")

        # 배지 — 지시서 포함 / 아동 플레이트
        badges = []
        if item.do_work_order:
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
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.ACCENT,
        ).grid(row=3, column=0, padx=8, pady=(2, 0), sticky="ew")

        # 출력 버튼
        self._btn = ctk.CTkButton(
            self,
            text="출력",
            height=30,
            command=self._handle_click,
            font=ctk.CTkFont(family=_font_family(), size=12, weight="bold"),
            fg_color=theme.ACCENT,
        )
        self._btn.grid(row=4, column=0, padx=8, pady=(4, 4), sticky="ew")

        # 상태 라벨 (전송 중/실패)
        self._status = ctk.CTkLabel(
            self,
            text="",
            anchor="center",
            font=ctk.CTkFont(family=_font_family(), size=10),
            text_color=theme.TEXT_MUTED,
        )
        self._status.grid(row=5, column=0, padx=8, pady=(0, 8), sticky="ew")

        self._load_thumb_async(item.download_path)

    def _load_thumb_async(self, path: str) -> None:
        def worker():
            img = _make_thumb(path, _THUMB_PX)
            if img is None:
                return
            # 메인 스레드에서 위젯 갱신
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

    def _handle_click(self) -> None:
        self._on_print(self.item_id)

    # ── 상태 전환 ──
    def set_printing(self, printer: str) -> None:
        self._btn.configure(state="disabled", text="전송 중…")
        suffix = f" · {printer}" if printer else ""
        self._status.configure(text=f"전송 중{suffix}", text_color=theme.ACCENT)

    def set_failed(self) -> None:
        self._btn.configure(state="normal", text="재시도", fg_color=theme.DANGER)
        self._status.configure(text="전송 실패 — 다시 시도하세요", text_color=theme.DANGER)


class DownloadGrid(ctk.CTkFrame):
    """READY 카드 그리드 컨테이너."""

    def __init__(self, parent, on_print: Callable[[str], None]) -> None:
        super().__init__(parent, fg_color="transparent")
        self._on_print = on_print
        self._cards: dict[str, DesignCard] = {}
        self._order: list[str] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._title = ctk.CTkLabel(
            self,
            text="출력 대기 0건",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=11, weight="bold"),
            text_color=theme.TEXT_MUTED,
        )
        self._title.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 2))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        for c in range(_COLS):
            self._scroll.grid_columnconfigure(c, weight=1, uniform="cards")

        self._empty = ctk.CTkLabel(
            self._scroll,
            text="출력 대기 중인 디자인이 없습니다.",
            font=ctk.CTkFont(family=_font_family(), size=12),
            text_color=theme.TEXT_MUTED,
        )
        self._render_empty()

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

    def set_failed(self, item_id: str) -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.set_failed()

    def restore(self, items) -> None:
        for it in items:
            self.add_item(it)

    def clear(self) -> None:
        for card in self._cards.values():
            card.destroy()
        self._cards.clear()
        self._order.clear()
        self._reflow()

    # ── 내부 ──
    def _reflow(self) -> None:
        for idx, item_id in enumerate(self._order):
            card = self._cards.get(item_id)
            if card is None:
                continue
            card.grid(row=idx // _COLS, column=idx % _COLS, padx=6, pady=6, sticky="nsew")
        count = len(self._order)
        self._title.configure(text=f"출력 대기 {count}건")
        if count == 0:
            self._render_empty()
        else:
            self._empty.grid_remove()

    def _render_empty(self) -> None:
        self._empty.grid(row=0, column=0, columnspan=_COLS, padx=12, pady=24)
