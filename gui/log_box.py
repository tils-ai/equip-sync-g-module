"""LogBox — rotating 로그 표시 + 자동 스크롤 (spec §7)."""

from __future__ import annotations

import logging
import queue

import customtkinter as ctk

from fonts import family as _font_family

from . import theme


class _QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.log_queue.put(self.format(record))
        except Exception:
            pass


class LogBox(ctk.CTkTextbox):
    MAX_LINES = 1000

    def __init__(self, parent) -> None:
        super().__init__(
            parent,
            state="disabled",
            fg_color=theme.LOG_BG,
            text_color=theme.LOG_TEXT,
            font=ctk.CTkFont(family=_font_family(), size=13),
            corner_radius=theme.CORNER_MD,
            wrap="none",
        )

    def append(self, line: str) -> None:
        self.configure(state="normal")
        self.insert("end", line + "\n")
        content = self.get("1.0", "end")
        lines = content.split("\n")
        if len(lines) > self.MAX_LINES:
            self.delete("1.0", f"{len(lines) - self.MAX_LINES}.0")
        self.configure(state="disabled")
        self.see("end")


def attach_logging(log_queue: queue.Queue) -> None:
    """루트 로거에 큐 핸들러를 추가 — main의 setup_logging 이후 호출."""
    handler = _QueueHandler(log_queue)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(handler)
