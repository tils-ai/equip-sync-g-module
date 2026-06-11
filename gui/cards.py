"""StatusCards — 한 줄 5개 카드: 대기/처리중/완료/오류/장비.

현장 글랜서빌리티: 봐야 할 카드가 색으로 떠오르게 — 오류>0 = DANGER tint,
대기>0 = ACCENT tint, 장비 상태 = tone별 tint + 아이콘.
상단 스트립이 컴팩트해야 하므로 숫자는 22(문서 권고 34에서 절충).
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from fonts import family as _font_family

from . import theme

_DEVICE_ICON = {"active": "⟳", "danger": "✕", "muted": "●"}
_DEVICE_TINT = {
    "active": theme.PROGRESS_SOFT,
    "danger": theme.DANGER_SOFT,
    "muted": theme.SURFACE,
}
_DEVICE_FG = {
    "active": theme.PROGRESS,
    "danger": theme.DANGER,
    "muted": theme.TEXT_MUTED,
}


class StatusCards(ctk.CTkFrame):
    def __init__(self, parent, *, on_error_click: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent, fg_color="transparent")
        self._on_error_click = on_error_click

        # 숫자 카드는 좁게 고정(좌우 여백 확보), 장비 카드만 텍스트라 넓게.
        _MINW = {"pending": 88, "processing": 88, "done": 88, "error": 88, "device": 150}

        self._values: dict[str, ctk.CTkLabel] = {}
        self._frames: dict[str, ctk.CTkFrame] = {}
        for i, (key, label) in enumerate(
            [("pending", "대기"), ("processing", "처리중"), ("done", "완료"),
             ("error", "오류"), ("device", "장비")]
        ):
            self.grid_columnconfigure(i, weight=0, minsize=_MINW[key])
            card = ctk.CTkFrame(
                self,
                corner_radius=theme.CORNER_MD,
                fg_color=theme.SURFACE,
                border_width=theme.BORDER_W,
                border_color=theme.BORDER,
            )
            card.grid(row=0, column=i, padx=theme.SP_1, pady=0, sticky="nsew")
            self._frames[key] = card

            ctk.CTkLabel(
                card,
                text=label,
                font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
                text_color=theme.TEXT_MUTED,
            ).pack(padx=theme.SP_3, pady=(theme.SP_2, 0))

            # 장비 카드는 텍스트 상태라 숫자 카드보다 작은 폰트, 기본 "-"
            is_device = key == "device"
            value = ctk.CTkLabel(
                card,
                text="-" if is_device else "0",
                font=ctk.CTkFont(
                    family=_font_family(),
                    size=theme.FONT_DEVICE if is_device else 22,
                    weight="bold",
                ),
                text_color=theme.TEXT_MUTED if is_device else theme.TEXT,
            )
            value.pack(padx=theme.SP_3, pady=(0, theme.SP_2))
            self._values[key] = value

            if key == "error" and on_error_click is not None:
                for w in (card, value):
                    w.bind("<Button-1>", lambda _e: on_error_click())
                    w.configure(cursor="hand2")

    def set_counts(self, *, pending: int, processing: int, done: int, error: int) -> None:
        self._values["pending"].configure(text=str(pending))
        self._values["processing"].configure(text=str(processing))
        self._values["done"].configure(text=str(done))
        self._values["error"].configure(text=str(error))

        # 봐야 할 카드를 tint 로 부각 — 오류>0 = DANGER, 대기>0 = ACCENT.
        self._values["error"].configure(text_color=theme.DANGER if error > 0 else theme.TEXT)
        self._frames["error"].configure(fg_color=theme.DANGER_SOFT if error > 0 else theme.SURFACE)
        self._values["pending"].configure(text_color=theme.ACCENT if pending > 0 else theme.TEXT)
        self._frames["pending"].configure(fg_color=theme.ACCENT_SOFT if pending > 0 else theme.SURFACE)

    def set_device(self, text: str, tone: str = "muted") -> None:
        """장비 상태 카드 갱신. tone: active/danger/muted — tint 배경 + 아이콘 + 색."""
        icon = _DEVICE_ICON.get(tone, "●")
        self._values["device"].configure(
            text=f"{icon} {text}",
            text_color=_DEVICE_FG.get(tone, theme.TEXT_MUTED),
        )
        self._frames["device"].configure(fg_color=_DEVICE_TINT.get(tone, theme.SURFACE))
