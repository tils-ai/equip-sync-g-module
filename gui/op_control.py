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
        # 컴팩트 2줄: [● Agent: detail] [버튼] / [● Watcher: detail] [버튼][폴더]
        # 상단 스트립에서 현황 카드와 한 줄로 나란히 두기 위한 고정 폭 레이아웃.
        self.grid_columnconfigure(1, weight=1)

        # Agent row
        self.agent_dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(family=_font_family(), size=13),
            text_color=theme.NEUTRAL,
        )
        self.agent_dot.grid(row=0, column=0, padx=(12, 6), pady=(8, 3), sticky="w")

        self.agent_text = ctk.CTkLabel(
            self,
            text="Agent: -",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=12),
            text_color=theme.TEXT,
        )
        self.agent_text.grid(row=0, column=1, sticky="ew", pady=(8, 3))

        self.agent_btn = ctk.CTkButton(
            self,
            text="시작",
            width=64,
            height=26,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_toggle_agent,
            state="disabled",
        )
        self.agent_btn.grid(row=0, column=2, columnspan=2, padx=(8, 12), pady=(8, 3), sticky="e")

        # Watcher row
        self.watcher_dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(family=_font_family(), size=13),
            text_color=theme.NEUTRAL,
        )
        self.watcher_dot.grid(row=1, column=0, padx=(12, 6), pady=(0, 8), sticky="w")

        self.watcher_text = ctk.CTkLabel(
            self,
            text="Watcher: 정지됨",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=12),
            text_color=theme.TEXT,
        )
        self.watcher_text.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        self.watcher_btn = ctk.CTkButton(
            self,
            text="정지",
            width=64,
            height=26,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_toggle_watcher,
        )
        self.watcher_btn.grid(row=1, column=2, padx=(8, 4), pady=(0, 8), sticky="e")

        ctk.CTkButton(
            self,
            text="폴더",
            width=56,
            height=26,
            font=ctk.CTkFont(family=_font_family(), size=11),
            command=on_open_folder,
        ).grid(row=1, column=3, padx=(0, 12), pady=(0, 8), sticky="e")

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
        # 마지막 활동 표시는 하단 "최근 처리" 리스트로 대체됨 — 상태만 보관.
        self._last_ts = time.time()
        self._last_summary = summary

    def tick(self) -> None:
        """1초마다 호출 — 현재는 갱신할 상대 시각 라벨 없음 (no-op)."""
