"""OpControlBox — Agent + Watcher 운영 컨트롤 (상태 칩 + 버튼 위계).

상단 스트립에서 현황 카드와 한 줄로 나란히. 상태는 점 단독이 아니라 옅은 tint 칩
(실행 중=SUCCESS_SOFT, 정지=IDLE_SOFT)으로 글랜서블하게. 시작=주 액션(ACCENT),
정지/폴더=보조(NEUTRAL_BTN) 로 위계 분리.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import customtkinter as ctk

from fonts import family as _font_family

from . import theme


class _StatusChip(ctk.CTkFrame):
    """[● 라벨: 상태] 옅은 tint 칩."""

    def __init__(self, parent, prefix: str) -> None:
        super().__init__(parent, corner_radius=theme.CORNER_SM, fg_color=theme.IDLE_SOFT)
        self._prefix = prefix
        self.grid_columnconfigure(1, weight=1)
        self._dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(family=_font_family(), size=12),
            text_color=theme.IDLE,
        )
        self._dot.grid(row=0, column=0, padx=(theme.SP_2, theme.SP_1), pady=theme.SP_1)
        self._text = ctk.CTkLabel(
            self,
            text=f"{prefix}: -",
            anchor="w",
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY),
            text_color=theme.TEXT,
        )
        self._text.grid(row=0, column=1, sticky="ew", padx=(0, theme.SP_2), pady=theme.SP_1)

    def update(self, *, running: bool, detail: str) -> None:
        self.configure(fg_color=theme.SUCCESS_SOFT if running else theme.IDLE_SOFT)
        self._dot.configure(text_color=theme.SUCCESS if running else theme.IDLE)
        self._text.configure(text=f"{self._prefix}: {detail}")


class OpControlBox(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        *,
        on_toggle_agent: Callable[[], None],
        on_toggle_watcher: Callable[[], None],
        on_open_folder: Callable[[], None],
    ) -> None:
        super().__init__(parent, corner_radius=theme.CORNER_MD, fg_color=theme.SURFACE,
                         border_width=theme.BORDER_W, border_color=theme.BORDER)
        self.grid_columnconfigure(0, weight=1)

        _BTN_H = 40  # 보조 컨트롤 — 주 액션(출력 56)보다 작게, 컴팩트 유지

        # Agent row
        self.agent_chip = _StatusChip(self, "Agent")
        self.agent_chip.grid(row=0, column=0, sticky="ew", padx=(theme.SP_3, theme.SP_2), pady=(theme.SP_2, theme.SP_1))
        self.agent_btn = ctk.CTkButton(
            self,
            text="시작",
            width=72,
            height=_BTN_H,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY, weight="bold"),
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            command=on_toggle_agent,
            state="disabled",
        )
        self.agent_btn.grid(row=0, column=1, columnspan=2, padx=(0, theme.SP_3), pady=(theme.SP_2, theme.SP_1), sticky="e")

        # Watcher row
        self.watcher_chip = _StatusChip(self, "Watcher")
        self.watcher_chip.grid(row=1, column=0, sticky="ew", padx=(theme.SP_3, theme.SP_2), pady=(theme.SP_1, theme.SP_2))
        self.watcher_btn = ctk.CTkButton(
            self,
            text="정지",
            width=72,
            height=_BTN_H,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY),
            fg_color=theme.NEUTRAL_BTN,
            hover_color=theme.NEUTRAL_HOVER,
            text_color=theme.TEXT,
            command=on_toggle_watcher,
        )
        self.watcher_btn.grid(row=1, column=1, padx=(0, theme.SP_1), pady=(theme.SP_1, theme.SP_2), sticky="e")

        ctk.CTkButton(
            self,
            text="폴더",
            width=64,
            height=_BTN_H,
            font=ctk.CTkFont(family=_font_family(), size=theme.FONT_BODY),
            fg_color=theme.NEUTRAL_BTN,
            hover_color=theme.NEUTRAL_HOVER,
            text_color=theme.TEXT,
            command=on_open_folder,
        ).grid(row=1, column=2, padx=(0, theme.SP_3), pady=(theme.SP_1, theme.SP_2), sticky="e")

        self._last_ts: Optional[float] = None
        self._last_summary: str = ""

    def set_agent(self, *, running: bool, detail: str, enabled: bool = False) -> None:
        self.agent_chip.update(running=running, detail=detail)
        self.agent_btn.configure(
            text="정지" if running else "시작",
            state="normal" if enabled else "disabled",
            fg_color=theme.NEUTRAL_BTN if running else theme.ACCENT,
            hover_color=theme.NEUTRAL_HOVER if running else theme.ACCENT_HOVER,
            text_color=theme.TEXT if running else theme.TEXT_ON_ACCENT,
        )

    def set_watcher(self, *, running: bool, detail: str) -> None:
        self.watcher_chip.update(running=running, detail=detail)
        self.watcher_btn.configure(text="정지" if running else "시작")

    def push_activity(self, summary: str) -> None:
        # 마지막 활동 표시는 하단 "최근 처리" 리스트로 대체됨 — 상태만 보관.
        self._last_ts = time.time()
        self._last_summary = summary

    def tick(self) -> None:
        """1초마다 호출 — 현재는 갱신할 상대 시각 라벨 없음 (no-op)."""
