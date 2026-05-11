"""Header — 장비명 + 페어링 상태 + 설정/테마 (spec §3)."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from fonts import family as _font_family

from . import theme


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
        super().__init__(parent, height=56, corner_radius=0, fg_color=theme.SURFACE)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text=device_label,
            font=ctk.CTkFont(family=_font_family(), size=14, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, padx=12, pady=12, sticky="w")

        self.pairing_dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(family=_font_family(), size=14),
            text_color=theme.NEUTRAL,
        )
        self.pairing_dot.grid(row=0, column=1, sticky="e", padx=(0, 4))

        self.pairing_text = ctk.CTkLabel(
            self,
            text="미페어링",
            font=ctk.CTkFont(family=_font_family(), size=12),
            text_color=theme.TEXT_MUTED,
        )
        self.pairing_text.grid(row=0, column=2, sticky="e", padx=(0, 12))

        ctk.CTkButton(
            self,
            text="⚙ 설정",
            width=72,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_settings,
        ).grid(row=0, column=3, padx=(0, 4))

        self.theme_menu = ctk.CTkOptionMenu(
            self,
            values=list(theme.APPEARANCE_LABELS.values()),
            width=90,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_theme_change,
        )
        self.theme_menu.set(theme.APPEARANCE_LABELS.get(appearance, "시스템"))
        self.theme_menu.grid(row=0, column=4, padx=(0, 12))

    def set_pairing(self, state: str) -> None:
        """state: 'connected' | 'unpaired' | 'error'"""
        color = {"connected": theme.SUCCESS, "unpaired": theme.NEUTRAL, "error": theme.DANGER}.get(
            state, theme.NEUTRAL
        )
        text = {"connected": "연결됨", "unpaired": "미페어링", "error": "오류"}.get(state, "미페어링")
        self.pairing_dot.configure(text_color=color)
        self.pairing_text.configure(text=text)
