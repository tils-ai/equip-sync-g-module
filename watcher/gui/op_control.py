"""OpControlBox — Agent + Watcher 운영 컨트롤 + 마지막 활동 (spec §5)."""

from __future__ import annotations

import time
from typing import Callable, Optional

import customtkinter as ctk

from fonts import family as _font_family

from . import theme


def relative_time(ts: Optional[float]) -> str:
    if ts is None:
        return "-"
    diff = time.time() - ts
    if diff < 10:
        return "방금"
    if diff < 60:
        return f"{int(diff)}초 전"
    if diff < 3600:
        return f"{int(diff / 60)}분 전"
    if diff < 86400:
        return f"{int(diff / 3600)}시간 전"
    return f"{int(diff / 86400)}일 전"


class OpControlBox(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        *,
        on_toggle_agent: Callable[[], None],
        on_toggle_watcher: Callable[[], None],
        on_open_folder: Callable[[], None],
    ) -> None:
        super().__init__(parent, corner_radius=theme.CORNER, fg_color=theme.SURFACE)
        self.grid_columnconfigure(1, weight=1)

        # Agent row
        self.agent_dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(family=_font_family(), size=14),
            text_color=theme.NEUTRAL,
        )
        self.agent_dot.grid(row=0, column=0, padx=(12, 6), pady=(10, 2), sticky="w")

        self.agent_text = ctk.CTkLabel(
            self,
            text="Agent: 비활성 (v0.3 예정)",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=12),
            text_color=theme.TEXT,
        )
        self.agent_text.grid(row=0, column=1, sticky="ew", pady=(10, 2))

        self.agent_btn = ctk.CTkButton(
            self,
            text="시작",
            width=80,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_toggle_agent,
            state="disabled",
        )
        self.agent_btn.grid(row=0, column=2, padx=(0, 12), pady=(10, 2))

        # Watcher row
        self.watcher_dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(family=_font_family(), size=14),
            text_color=theme.NEUTRAL,
        )
        self.watcher_dot.grid(row=1, column=0, padx=(12, 6), sticky="w")

        self.watcher_text = ctk.CTkLabel(
            self,
            text="Watcher: 정지됨",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=12),
            text_color=theme.TEXT,
        )
        self.watcher_text.grid(row=1, column=1, sticky="ew")

        self.watcher_btn = ctk.CTkButton(
            self,
            text="정지",
            width=80,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_toggle_watcher,
        )
        self.watcher_btn.grid(row=1, column=2, padx=(0, 12))

        ctk.CTkButton(
            self,
            text="폴더 열기",
            width=80,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_open_folder,
        ).grid(row=1, column=3, padx=(0, 12))

        # Last activity
        self.activity = ctk.CTkLabel(
            self,
            text="마지막 활동: -",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=11),
            text_color=theme.TEXT_MUTED,
        )
        self.activity.grid(row=2, column=0, columnspan=4, sticky="ew", padx=12, pady=(2, 10))

        self._last_ts: Optional[float] = None
        self._last_summary: str = ""

    def set_agent(self, *, running: bool, detail: str, enabled: bool = False) -> None:
        self.agent_dot.configure(text_color=theme.SUCCESS if running else theme.NEUTRAL)
        self.agent_text.configure(text=f"Agent: {detail}")
        self.agent_btn.configure(text="정지" if running else "시작", state="normal" if enabled else "disabled")

    def set_watcher(self, *, running: bool, detail: str) -> None:
        self.watcher_dot.configure(text_color=theme.SUCCESS if running else theme.NEUTRAL)
        self.watcher_text.configure(text=f"Watcher: {detail}")
        self.watcher_btn.configure(text="정지" if running else "시작")

    def push_activity(self, summary: str) -> None:
        self._last_ts = time.time()
        self._last_summary = summary
        self._refresh_activity()

    def _refresh_activity(self) -> None:
        if self._last_ts is None:
            self.activity.configure(text="마지막 활동: -")
        else:
            self.activity.configure(text=f"마지막 활동: {relative_time(self._last_ts)} — {self._last_summary}")

    def tick(self) -> None:
        """1초마다 호출 — 상대 시각 갱신."""
        self._refresh_activity()
