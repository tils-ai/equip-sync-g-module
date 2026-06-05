"""가먼트 프린터 장비 상태 폴러 — status CSV 를 주기 조회해 GUI 에 노출.

agent.py 의 풀링 루프(서버 작업)와 독립된 daemon 스레드로 동작한다.
send 가 블로킹이라 출력 중에도 장비 상태(출력중/에러)를 읽으려면 별도 스레드가 필요하다.
"""

import logging
import threading
import time
from typing import Callable, Optional

import config
from garment_cli import read_printer_status

logger = logging.getLogger(__name__)


def _fire(cb, *args):
    """콜백을 안전하게 호출 — 미지정이거나 예외면 무시."""
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        logger.exception("장비 상태 콜백 예외 — 무시하고 계속")


class DeviceStatusPoller:
    """프린터 장비 상태를 주기적으로 폴링하는 백그라운드 스레드."""

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self.latest: dict | None = None
        self._prev_error = False  # 에러 엣지 감지용 (정상→에러일 때만 알림)
        # 에러 진입 시 1회 호출 (status dict 전달)
        self.on_error: Optional[Callable[[dict], None]] = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return
        if not config.DEVICE_STATUS_ENABLED or config.DEVICE_STATUS_INTERVAL <= 0:
            logger.info("장비 상태 폴링 비활성 (status_enabled/status_interval 설정)")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("장비 상태 폴링 시작 — %d초 간격", config.DEVICE_STATUS_INTERVAL)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self):
        while self._running:
            try:
                status = read_printer_status(config.GARMENT_PRINTER_NAME)
                self.latest = status
                self._check_error_edge(status)
            except Exception:
                logger.exception("장비 상태 폴링 예외 — 다음 주기에 재시도")
                self.latest = None

            interval = max(config.DEVICE_STATUS_INTERVAL, 1)
            waited = 0.0
            while waited < interval and self._running:
                time.sleep(1)
                waited += 1

    def _check_error_edge(self, status: dict | None):
        """정상→에러 전이에서만 on_error 호출(매 주기 중복 알림 방지)."""
        is_error = bool(status and status.get("error"))
        if is_error and not self._prev_error:
            _fire(self.on_error, status)
        self._prev_error = is_error
