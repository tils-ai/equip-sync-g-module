"""Header — 장비명 + 페어링 상태(칩) + 설정/테마(보조 액션)."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from fonts import family as _font_family

from . import theme

_PAIR = {
    "connected": ("●", "연결됨", theme.SUCCESS, theme.SUCCESS_SOFT),
    "unpaired": ("●", "미페어링", theme.IDLE, theme.IDLE_SOFT),
    "error": ("✕", "오류", theme.DANGER, theme.DANGER_SOFT),
}


class Header(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        *,
        device_label: str,
        on_settings: Callable[[], None],
        on_theme_change: Callable[[str], None],
        appearance: str,
    ) -> None:
        super().__init__(parent, height=64, corner_radius=0, fg_color=theme.SURFACE,
                         border_width=theme.BORDER_W, border_color=theme.BORDER)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text=device_label,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_TITLE, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, padx=theme.SP_3, pady=theme.SP_3, sticky="w")

        # 페어링 상태 칩 (점 + 텍스트 + tint 배경)
        self._pair_chip = ctk.CTkFrame(self, corner_radius=theme.CORNER_SM, fg_color=theme.IDLE_SOFT)
        self._pair_chip.grid(row=0, column=1, sticky="e", padx=(0, theme.SP_2))
        self._pair_dot = ctk.CTkLabel(
            self._pair_chip,
            text="●",
            font=ctk.CTkFont(family=_font_family(), size=13),
            text_color=theme.IDLE,
        )
        self._pair_dot.grid(row=0, column=0, padx=(theme.SP_2, theme.SP_1), pady=theme.SP_1)
        self._pair_text = ctk.CTkLabel(
            self._pair_chip,
            text="미페어링",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            text_color=theme.TEXT_SUB,
        )
        self._pair_text.grid(row=0, column=1, padx=(0, theme.SP_2), pady=theme.SP_1)

        ctk.CTkButton(
            self,
            text="⚙ 설정",
            width=80,
            height=theme.TOUCH_MIN - 8,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            fg_color=theme.NEUTRAL_BTN,
            hover_color=theme.NEUTRAL_HOVER,
            text_color=theme.TEXT,
            command=on_settings,
        ).grid(row=0, column=2, padx=(0, theme.SP_1))

        self.theme_menu = ctk.CTkOptionMenu(
            self,
            values=list(theme.APPEARANCE_LABELS.values()),
            width=96,
            height=theme.TOUCH_MIN - 8,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            dropdown_font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION),
            fg_color=theme.NEUTRAL_BTN,
            button_color=theme.NEUTRAL_BTN,
            button_hover_color=theme.NEUTRAL_HOVER,
            text_color=theme.TEXT,
            command=on_theme_change,
        )
        self.theme_menu.set(theme.APPEARANCE_LABELS.get(appearance, "시스템"))
        self.theme_menu.grid(row=0, column=3, padx=(0, theme.SP_3))

    def set_pairing(self, state: str) -> None:
        """state: 'connected' | 'unpaired' | 'error'"""
        icon, text, fg, soft = _PAIR.get(state, _PAIR["unpaired"])
        self._pair_chip.configure(fg_color=soft)
        self._pair_dot.configure(text=icon, text_color=fg)
        self._pair_text.configure(text=text)
