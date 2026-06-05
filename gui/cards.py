"""StatusCards — 한 줄 4개 카드: 대기/처리중/완료/오류 (spec §4)."""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from fonts import family as _font_family

from . import theme


class StatusCards(ctk.CTkFrame):
    def __init__(self, parent, *, on_error_click: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent, fg_color="transparent")
        self._on_error_click = on_error_click

        for i in range(5):
            self.grid_columnconfigure(i, weight=1)

        self._values: dict[str, ctk.CTkLabel] = {}
        for i, (key, label) in enumerate(
            [("pending", "대기"), ("processing", "처리중"), ("done", "완료"),
             ("error", "오류"), ("device", "장비")]
        ):
            card = ctk.CTkFrame(self, corner_radius=theme.CORNER, fg_color=theme.SURFACE)
            card.grid(row=0, column=i, padx=4, pady=4, sticky="nsew")

            ctk.CTkLabel(
                card,
                text=label,
                font=ctk.CTkFont(family=_font_family(), size=11),
                text_color=theme.TEXT_MUTED,
            ).pack(pady=(8, 0))

            # 장비 카드는 텍스트 상태라 숫자 카드보다 작은 폰트, 기본 "-"
            is_device = key == "device"
            value = ctk.CTkLabel(
                card,
                text="-" if is_device else "0",
                font=ctk.CTkFont(
                    family=_font_family(),
                    size=14 if is_device else 22,
                    weight="bold",
                ),
                text_color=theme.TEXT_MUTED if is_device else theme.TEXT,
            )
            value.pack(pady=(0, 8))
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
        self._values["error"].configure(
            text_color=theme.DANGER if error > 0 else theme.TEXT
        )

    _DEVICE_TONES = {
        "active": theme.ACCENT,
        "danger": theme.DANGER,
        "muted": theme.TEXT_MUTED,
    }

    def set_device(self, text: str, tone: str = "muted") -> None:
        """장비 상태 카드 갱신. tone: active/danger/muted."""
        self._values["device"].configure(
            text=text,
            text_color=self._DEVICE_TONES.get(tone, theme.TEXT_MUTED),
        )
