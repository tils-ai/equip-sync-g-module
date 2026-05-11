"""세션 누적 카운터 — 앱 시작 시 0으로 시작, 종료/재시작 시 리셋."""

from __future__ import annotations

import threading


class SessionStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.done = 0
        self.error = 0

    def on_done(self) -> None:
        with self._lock:
            self.done += 1

    def on_error(self) -> None:
        with self._lock:
            self.error += 1

    def reset(self) -> None:
        with self._lock:
            self.done = 0
            self.error = 0
