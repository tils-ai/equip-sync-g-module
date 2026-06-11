"""RecentList — 최근 처리 5건 표시 (spec §6, ring buffer)."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import customtkinter as ctk

from fonts import family as _font_family

from . import theme

_ICONS = {"ok": "✅", "warn": "⚠️", "error": "❌"}


@dataclass
class ActivityItem:
    ts: float
    label: str
    status: str  # "ok" | "warn" | "error"
    detail: str = ""


class RecentList(ctk.CTkFrame):
    def __init__(self, parent, *, max_items: int = 5) -> None:
        super().__init__(parent, fg_color="transparent")
        self.max_items = max_items
        self.items: deque[ActivityItem] = deque(maxlen=max_items)
        self.grid_columnconfigure(0, weight=1)

        self._title = ctk.CTkLabel(
            self,
            text="최근 처리",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_CAPTION, weight="bold"),
            text_color=theme.TEXT_MUTED,
        )
        self._title.grid(row=0, column=0, sticky="ew", padx=theme.SP_3, pady=(theme.SP_2, theme.SP_1))

        self._labels: list[ctk.CTkLabel] = []
        for i in range(max_items):
            lab = ctk.CTkLabel(
                self,
                text="",
                anchor="w",
                font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY),
                text_color=theme.TEXT,
            )
            lab.grid(row=i + 1, column=0, sticky="ew", padx=theme.SP_3, pady=theme.SP_1)
            self._labels.append(lab)

    def push(self, item: ActivityItem) -> None:
        self.items.appendleft(item)
        self._render()

    def _render(self) -> None:
        for i, lab in enumerate(self._labels):
            if i < len(self.items):
                it = self.items[i]
                ts = time.strftime("%H:%M", time.localtime(it.ts))
                icon = _ICONS.get(it.status, "·")
                detail = f" {it.detail}" if it.detail else ""
                lab.configure(
                    text=f"· {ts}  {it.label}  {icon}{detail}",
                    text_color=theme.DANGER if it.status == "error" else theme.TEXT,
                )
            else:
                lab.configure(text="")
